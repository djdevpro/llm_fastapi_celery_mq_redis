"""
FastAPI LLM Streaming avec RabbitMQ - Architecture scalable.

Deux modes disponibles :
1. /chat (ancien) - Traitement synchrone, streaming direct
2. /chat/async (nouveau) - Fire-and-forget, traité par workers
"""
import asyncio
import uuid
import json
import logging
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from services.rabbit_publisher import RabbitPublisher
from services.rabbit_consumer import RabbitConsumer
from services.connection_pool import get_pool
from config import OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-mq")

# Queue des tâches pour les workers
TASK_QUEUE = "llm_tasks"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie - connexions partagées."""
    logger.info("Démarrage de l'application...")
    # Initialise le pool au démarrage
    try:
        pool = get_pool()
        logger.info("Pool RabbitMQ prêt")
    except Exception as e:
        logger.warning(f"RabbitMQ non disponible au démarrage: {e}")
    
    yield
    
    # Cleanup à l'arrêt
    logger.info("Arrêt de l'application...")
    try:
        get_pool().close()
    except:
        pass


app = FastAPI(
    title="LLM Streaming + RabbitMQ (Scalable)",
    lifespan=lifespan
)

# CORS pour le client HTML
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],
)

# Client OpenAI async global
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
logger.info("OpenAI client créé")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str = "gpt-4o-mini"


# ============================================================
# ENDPOINTS SANTÉ
# ============================================================

@app.get("/health")
async def health():
    """Health check basique."""
    return {"status": "ok"}


@app.get("/health/full")
async def health_full():
    """Health check complet avec statut RabbitMQ (timeout 3s)."""
    rabbit_ok = False
    try:
        def check_rabbit():
            pool = get_pool()
            with pool.channel() as ch:
                return ch.is_open
        
        # Timeout de 3 secondes
        rabbit_ok = await asyncio.wait_for(
            asyncio.to_thread(check_rabbit),
            timeout=3.0
        )
    except asyncio.TimeoutError:
        pass
    except:
        pass
    
    return {
        "status": "ok" if rabbit_ok else "degraded",
        "rabbitmq": "connected" if rabbit_ok else "disconnected",
        "openai": "configured" if OPENAI_API_KEY else "missing"
    }


@app.get("/test", response_class=PlainTextResponse)
async def test_openai():
    """Test rapide OpenAI (async)."""
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10
        )
        return f"OK: {response.choices[0].message.content}"
    except Exception as e:
        logger.error(f"Test Error: {e}", exc_info=True)
        return f"ERROR: {e}"


# ============================================================
# MODE SYNCHRONE (ancien) - Pour compatibilité
# ============================================================

@app.post("/chat")
async def chat_sync(request: ChatRequest):
    """
    Chat avec streaming synchrone + publication RabbitMQ.
    Mode compatibilité - utilise /chat/async pour plus de charge.
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    async def generate():
        # Connexion RabbitMQ dans un thread
        publisher = RabbitPublisher(session_id)
        try:
            await asyncio.to_thread(publisher.connect)
        except Exception as e:
            yield f"[ERROR: RabbitMQ - {e}]"
            return

        try:
            # Stream OpenAI async
            stream = await openai_client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": "Tu es un assistant utile et concis."},
                    {"role": "user", "content": request.message}
                ],
                stream=True
            )

            full_response = ""
            async for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_response += content
                    # Publish dans un thread (non bloquant)
                    await asyncio.to_thread(publisher.publish, {"type": "chunk", "chunk": content})
                    yield content

            await asyncio.to_thread(publisher.publish, {"type": "complete"})
            logger.info(f"Session {session_id} done ({len(full_response)} chars)")

        except Exception as e:
            logger.error(f"Stream Error: {e}")
            await asyncio.to_thread(publisher.publish, {"type": "error", "error": str(e)})
            yield f"[ERROR: {e}]"
        finally:
            await asyncio.to_thread(publisher.close)

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"X-Session-ID": session_id}
    )


# ============================================================
# MODE ASYNCHRONE (nouveau) - Fire-and-forget pour haute charge
# ============================================================

@app.post("/chat/async")
async def chat_async(request: ChatRequest):
    """
    Chat asynchrone - Fire-and-forget.
    
    1. Envoie la tâche dans RabbitMQ
    2. Retourne immédiatement avec le session_id
    3. Le client écoute sur /stream/{session_id}
    
    Avantages :
    - Libère le worker HTTP instantanément
    - Traitement par workers LLM dédiés
    - Scale horizontalement
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    task = {
        "session_id": session_id,
        "message": request.message,
        "model": request.model
    }
    
    try:
        # Publie dans un thread pour ne pas bloquer l'event loop
        def publish_task():
            pool = get_pool()
            pool.publish(
                queue=TASK_QUEUE,
                message=json.dumps(task).encode(),
                declare=True
            )
        
        await asyncio.to_thread(publish_task)
        logger.info(f"Tâche envoyée: {session_id[:8]}...")
        
        return JSONResponse(
            content={
                "status": "queued",
                "session_id": session_id,
                "stream_url": f"/stream/{session_id}"
            },
            headers={"X-Session-ID": session_id}
        )
        
    except Exception as e:
        logger.error(f"Erreur queue: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"RabbitMQ indisponible: {e}"
        )


# ============================================================
# STREAMING SSE (consommation des réponses)
# ============================================================

@app.get("/stream/{session_id}")
async def stream_from_mq(session_id: str):
    """SSE depuis RabbitMQ - Consomme les chunks d'une session."""
    async def events():
        consumer = RabbitConsumer(session_id)
        await asyncio.to_thread(consumer.connect)
        try:
            async for chunk in consumer.consume_session():
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            await asyncio.to_thread(consumer.close)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# ============================================================
# STATS (monitoring)
# ============================================================

@app.get("/stats")
async def get_stats():
    """Statistiques des queues RabbitMQ (avec timeout)."""
    try:
        def fetch_stats():
            pool = get_pool()
            with pool.channel() as ch:
                # Déclare la queue (la crée si n'existe pas)
                result = ch.queue_declare(
                    queue=TASK_QUEUE,
                    durable=True,
                    arguments={"x-message-ttl": 300000}
                )
                return result.method.message_count
        
        # Timeout de 5 secondes max
        pending_tasks = await asyncio.wait_for(
            asyncio.to_thread(fetch_stats),
            timeout=5.0
        )
        
        return {
            "pending_tasks": pending_tasks,
            "queue": TASK_QUEUE,
            "status": "ok"
        }
    except asyncio.TimeoutError:
        return {
            "pending_tasks": -1,
            "error": "timeout",
            "status": "slow"
        }
    except Exception as e:
        return {
            "pending_tasks": -1,
            "error": str(e),
            "status": "error"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
