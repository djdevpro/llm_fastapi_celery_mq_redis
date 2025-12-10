"""
FastAPI + Celery - API LLM scalable.

Endpoints:
- POST /chat    → Fire-and-forget (Celery task)
- GET  /chat/{task_id} → Status d'une tâche
- GET  /stream/{session_id} → SSE streaming depuis Redis
- POST /embeddings    → Batch embeddings async
"""
import asyncio
import json
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import redis.asyncio as aioredis

from celery.result import AsyncResult
from app.celery_app import celery
from app.tasks.llm_tasks import chat_completion, batch_embeddings
from app.config import OPENAI_API_KEY, REDIS_URL
from app.api.proxy import router as proxy_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-api")

# Clients async
redis_client: Optional[aioredis.Redis] = None
openai_client: Optional[AsyncOpenAI] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    global redis_client, openai_client
    
    redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis connecté")
    
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client prêt")
    
    yield
    
    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="LLM API",
    description="API LLM scalable avec Celery + Redis",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "X-Task-ID", "X-Request-ID"],
)

# Proxy OpenAI compatible
app.include_router(proxy_router)


# ============================================================
# MODELS
# ============================================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: str = "gpt-4o-mini"
    system_prompt: str = "Tu es un assistant utile et concis."
    stream: bool = True
    priority: int = Field(default=0, ge=-10, le=10)
    user_id: Optional[str] = None


class EmbeddingsRequest(BaseModel):
    texts: list[str]
    model: str = "text-embedding-3-small"
    user_id: Optional[str] = None


class TaskResponse(BaseModel):
    status: str
    task_id: str
    session_id: str
    stream_url: str


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():
    return {"status": "ok", "backend": "celery+redis"}


@app.get("/health/full")
async def health_full():
    redis_ok = False
    celery_ok = False
    
    try:
        await redis_client.ping()
        redis_ok = True
    except:
        pass
    
    try:
        stats = celery.control.inspect().stats()
        celery_ok = stats is not None and len(stats) > 0
    except:
        pass
    
    return {
        "status": "ok" if (redis_ok and celery_ok) else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "celery_workers": "active" if celery_ok else "no_workers",
        "openai": "configured" if OPENAI_API_KEY else "missing"
    }


# ============================================================
# CHAT ASYNC (Celery)
# ============================================================

@app.post("/chat", response_model=TaskResponse)
async def chat(request: ChatRequest):
    """Chat asynchrone via Celery."""
    session_id = request.session_id or str(uuid.uuid4())
    
    # Détermine la queue selon priorité
    queue = "high" if request.priority > 5 else "low" if request.priority < -5 else "default"
    
    # Construire les paramètres OpenAI
    completion_params = {
        "model": request.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.message}
        ],
        "stream": request.stream,
    }
    if request.user_id:
        completion_params["user"] = request.user_id
    
    task = chat_completion.apply_async(
        kwargs={
            "session_id": session_id,
            "completion_params": completion_params,
        },
        queue=queue,
        priority=request.priority + 10,
    )
    
    logger.info(f"Task {task.id} queued (queue: {queue})")
    
    return TaskResponse(
        status="queued",
        task_id=task.id,
        session_id=session_id,
        stream_url=f"/stream/{session_id}"
    )


@app.get("/chat/{task_id}")
async def get_task_status(task_id: str):
    """Status d'une tâche Celery."""
    result = AsyncResult(task_id, app=celery)
    
    response = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
    }
    
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    
    return response


# ============================================================
# STREAMING SSE
# ============================================================

@app.get("/stream/{session_id}")
async def stream_sse(
    session_id: str,
    timeout: int = Query(default=900, le=1800)
):
    """SSE streaming depuis Redis pub/sub. Timeout configurable (défaut 15 min, max 30 min)."""
    async def event_generator():
        channel = f"llm:stream:{session_id}"
        pubsub = redis_client.pubsub()
        
        try:
            await pubsub.subscribe(channel)
            start_time = asyncio.get_event_loop().time()
            
            async for message in pubsub.listen():
                if asyncio.get_event_loop().time() - start_time > timeout:
                    yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                    break
                
                if message["type"] == "message":
                    data = message['data']
                    # Décoder si bytes
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    
                    yield f"data: {data}\n\n"
                    
                    try:
                        parsed = json.loads(data)
                        if parsed.get("type") in ("complete", "error"):
                            break
                    except:
                        pass
                        
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# ============================================================
# EMBEDDINGS
# ============================================================

@app.post("/embeddings")
async def create_embeddings(request: EmbeddingsRequest):
    if len(request.texts) > 100:
        raise HTTPException(400, "Maximum 100 textes par requête")
    
    task = batch_embeddings.apply_async(
        kwargs={"texts": request.texts, "model": request.model}
    )
    
    return {"status": "queued", "task_id": task.id, "status_url": f"/embeddings/{task.id}"}


@app.get("/embeddings/{task_id}")
async def get_embeddings_result(task_id: str):
    result = AsyncResult(task_id, app=celery)
    
    if not result.ready():
        return {"status": result.status, "ready": False}
    
    if result.successful():
        return {"status": "SUCCESS", "ready": True, "result": result.result}
    else:
        raise HTTPException(500, f"Task failed: {result.result}")


# ============================================================
# STATS
# ============================================================

@app.get("/stats")
async def get_stats():
    stats = {"queues": {}, "workers": 0, "status": "ok"}
    
    try:
        for queue_name in ["high", "default", "low"]:
            length = await redis_client.llen(queue_name)
            stats["queues"][queue_name] = length
        
        active = celery.control.inspect().active()
        if active:
            stats["workers"] = len(active)
            stats["active_tasks"] = sum(len(tasks) for tasks in active.values())
            
    except Exception as e:
        stats["status"] = "error"
        stats["error"] = str(e)
    
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
