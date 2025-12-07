"""
FastAPI + Celery - Architecture scalable pour LLM.

Endpoints:
- POST /chat          → Synchrone (streaming direct)
- POST /chat/async    → Fire-and-forget (Celery task)
- GET  /chat/{task_id} → Status d'une tâche
- GET  /stream/{session_id} → SSE streaming depuis Redis pub/sub
- POST /embeddings    → Batch embeddings async

Lancer:
    uvicorn main_celery:app --reload --port 8007
    celery -A celery_app worker --loglevel=info -c 4
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
from celery_app import celery
from tasks.llm_tasks import chat_completion, batch_embeddings
from config import OPENAI_API_KEY, REDIS_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-celery")

# Redis async client
redis_client: Optional[aioredis.Redis] = None

# OpenAI async client
openai_client: Optional[AsyncOpenAI] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    global redis_client, openai_client
    
    # Init Redis async
    redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis connecté")
    
    # Init OpenAI async
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client prêt")
    
    yield
    
    # Cleanup
    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="LLM API - Celery + Redis",
    description="Architecture scalable avec rate limiting et priorités",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "X-Task-ID"],
)


# ============================================================
# MODELS
# ============================================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: str = "gpt-4o-mini"
    system_prompt: str = "Tu es un assistant utile et concis."
    stream: bool = True
    priority: int = Field(default=0, ge=-10, le=10, description="Priorité (-10 low, 0 default, 10 high)")
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
    """Health check."""
    return {"status": "ok", "backend": "celery+redis"}


@app.get("/health/full")
async def health_full():
    """Health check complet."""
    redis_ok = False
    celery_ok = False
    
    try:
        await redis_client.ping()
        redis_ok = True
    except:
        pass
    
    try:
        # Check Celery workers
        inspect = celery.control.inspect()
        stats = inspect.stats()
        celery_ok = stats is not None and len(stats) > 0
    except:
        pass
    
    status = "ok" if (redis_ok and celery_ok) else "degraded"
    
    return {
        "status": status,
        "redis": "connected" if redis_ok else "disconnected",
        "celery_workers": "active" if celery_ok else "no_workers",
        "openai": "configured" if OPENAI_API_KEY else "missing"
    }


# ============================================================
# CHAT SYNCHRONE (streaming direct)
# ============================================================

@app.post("/chat")
async def chat_sync(request: ChatRequest):
    """
    Chat avec streaming synchrone.
    
    Pour des cas où le streaming temps réel est critique.
    Ne passe pas par Celery - exécuté directement.
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    async def generate():
        try:
            stream = await openai_client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.message}
                ],
                stream=True
            )
            
            async for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content
                    
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"\n[ERROR: {e}]"
    
    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"X-Session-ID": session_id}
    )


# ============================================================
# CHAT ASYNC (Celery task)
# ============================================================

@app.post("/chat/async", response_model=TaskResponse)
async def chat_async(request: ChatRequest):
    """
    Chat asynchrone via Celery.
    
    1. Envoie la tâche dans la queue (avec priorité)
    2. Retourne immédiatement avec task_id
    3. Le client écoute sur /stream/{session_id} pour les chunks
    
    Avantages:
    - Rate limiting distribué
    - Retry automatique
    - Priorité des tâches
    - Scalable horizontalement
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    # Détermine la queue selon priorité
    if request.priority > 5:
        queue = "high"
    elif request.priority < -5:
        queue = "low"
    else:
        queue = "default"
    
    # Envoie la tâche
    task = chat_completion.apply_async(
        kwargs={
            "session_id": session_id,
            "message": request.message,
            "model": request.model,
            "system_prompt": request.system_prompt,
            "stream": request.stream,
            "user_id": request.user_id,
        },
        queue=queue,
        priority=request.priority + 10,  # Celery priority: 0-20
    )
    
    logger.info(f"Task {task.id} queued (session: {session_id}, queue: {queue})")
    
    return TaskResponse(
        status="queued",
        task_id=task.id,
        session_id=session_id,
        stream_url=f"/stream/{session_id}"
    )


# ============================================================
# TASK STATUS
# ============================================================

@app.get("/chat/{task_id}")
async def get_task_status(task_id: str):
    """
    Récupère le statut d'une tâche Celery.
    
    States: PENDING, STARTED, SUCCESS, FAILURE, RETRY
    """
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
    elif result.status == "STARTED":
        response["info"] = result.info
    
    return response


# ============================================================
# STREAMING SSE (Redis pub/sub)
# ============================================================

@app.get("/stream/{session_id}")
async def stream_sse(
    session_id: str,
    timeout: int = Query(default=120, le=300, description="Timeout en secondes")
):
    """
    SSE streaming depuis Redis pub/sub.
    
    Le client s'abonne et reçoit les chunks en temps réel
    publiés par le worker Celery.
    """
    async def event_generator():
        channel = f"llm:stream:{session_id}"
        pubsub = redis_client.pubsub()
        
        try:
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to {channel}")
            
            start_time = asyncio.get_event_loop().time()
            
            async for message in pubsub.listen():
                # Check timeout
                if asyncio.get_event_loop().time() - start_time > timeout:
                    yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                    break
                
                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    
                    # Parse pour détecter la fin
                    try:
                        parsed = json.loads(data)
                        if parsed.get("type") in ("complete", "error"):
                            break
                    except:
                        pass
                        
        except asyncio.CancelledError:
            logger.info(f"Stream {session_id} cancelled")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id
        }
    )


# ============================================================
# EMBEDDINGS ASYNC
# ============================================================

@app.post("/embeddings")
async def create_embeddings(request: EmbeddingsRequest):
    """
    Génère des embeddings en batch (async).
    
    Utile pour RAG, semantic search, etc.
    """
    if len(request.texts) > 100:
        raise HTTPException(400, "Maximum 100 textes par requête")
    
    task = batch_embeddings.apply_async(
        kwargs={
            "texts": request.texts,
            "model": request.model,
            "user_id": request.user_id,
        }
    )
    
    return {
        "status": "queued",
        "task_id": task.id,
        "status_url": f"/embeddings/{task.id}"
    }


@app.get("/embeddings/{task_id}")
async def get_embeddings_result(task_id: str):
    """Récupère le résultat des embeddings."""
    result = AsyncResult(task_id, app=celery)
    
    if not result.ready():
        return {"status": result.status, "ready": False}
    
    if result.successful():
        return {"status": "SUCCESS", "ready": True, "result": result.result}
    else:
        raise HTTPException(500, f"Task failed: {result.result}")


# ============================================================
# QUEUE STATS
# ============================================================

@app.get("/stats")
async def get_stats():
    """Statistiques des queues et workers."""
    stats = {
        "queues": {},
        "workers": 0,
        "status": "ok"
    }
    
    try:
        # Queue lengths via Redis
        for queue_name in ["high", "default", "low"]:
            length = await redis_client.llen(queue_name)
            stats["queues"][queue_name] = length
        
        # Worker count
        inspect = celery.control.inspect()
        active = inspect.active()
        if active:
            stats["workers"] = len(active)
            stats["active_tasks"] = sum(len(tasks) for tasks in active.values())
            
    except Exception as e:
        stats["status"] = "error"
        stats["error"] = str(e)
    
    return stats


# ============================================================
# ADMIN
# ============================================================

@app.post("/admin/purge/{queue}")
async def purge_queue(queue: str):
    """Purge une queue (admin only)."""
    if queue not in ["high", "default", "low"]:
        raise HTTPException(400, "Queue invalide")
    
    celery.control.purge()
    return {"status": "purged", "queue": queue}


@app.post("/admin/revoke/{task_id}")
async def revoke_task(task_id: str, terminate: bool = False):
    """Annule une tâche."""
    celery.control.revoke(task_id, terminate=terminate)
    return {"status": "revoked", "task_id": task_id, "terminated": terminate}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
