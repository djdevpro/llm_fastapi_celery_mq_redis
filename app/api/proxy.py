"""
Proxy compatible OpenAI API.

Les clients utilisent le SDK OpenAI standard avec base_url pointant vers ce proxy.
Le proxy queue les requêtes via Celery pour gérer la charge.

Usage client:
    from openai import OpenAI
    client = OpenAI(base_url="http://localhost:8007/v1", api_key="any")
    response = client.chat.completions.create(...)
"""
import asyncio
import json
import time
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis

# Types OpenAI natifs
from openai import OpenAI
from openai.types import Model
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
)
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice, ChoiceDelta
from openai.types.completion_usage import CompletionUsage

from app.config import REDIS_URL, OPENAI_API_KEY, API_TIMEOUT
from app.tasks.llm_tasks import chat_completion as chat_completion_task

router = APIRouter(prefix="/v1", tags=["OpenAI Proxy"])

# Redis client (sera initialisé via lifespan de main.py)
redis_client: Optional[aioredis.Redis] = None

# Client OpenAI pour récupérer les modèles
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/chat/completions")
async def chat_completions(
    request: dict,
    authorization: Optional[str] = Header(None)
):
    """
    Endpoint compatible OpenAI /v1/chat/completions.
    
    Accepte TOUS les paramètres OpenAI natifs et les passe directement à l'API.
    
    Paramètres supportés (non exhaustif, tout ce que OpenAI supporte):
    - model, messages (requis)
    - temperature, top_p, max_tokens, max_completion_tokens
    - response_format (json_object, json_schema, text)
    - reasoning_effort (low, medium, high) - pour o1/o3
    - tools, tool_choice, parallel_tool_calls
    - frequency_penalty, presence_penalty
    - stop, n, seed, logprobs, top_logprobs
    - stream, stream_options
    - user, metadata, store
    - modalities, audio, prediction
    - service_tier, etc.
    
    Extension proxy:
    - priority: int [-10, 10] pour la queue (high > 5, low < -5, default sinon)
    """
    session_id = str(uuid.uuid4())
    request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    
    # Extraire l'extension proxy et la retirer des params OpenAI
    priority = request.pop("priority", 0)
    
    # Valider la présence de messages
    if not request.get("messages"):
        raise HTTPException(400, "messages field is required")
    
    # Paramètres OpenAI (tout le reste)
    completion_params = request
    model = completion_params.get("model", "gpt-4o-mini")
    stream = completion_params.get("stream", False)
    
    # Déterminer la queue basée sur la priorité
    queue = "high" if priority > 5 else "low" if priority < -5 else "default"
    
    # Queue la tâche Celery avec TOUS les paramètres OpenAI
    task = chat_completion_task.apply_async(
        kwargs={
            "session_id": session_id,
            "completion_params": completion_params,
        },
        queue=queue,
    )
    
    if stream:
        return StreamingResponse(
            _stream_response(session_id, request_id, model),
            media_type="text/event-stream",
            headers={"X-Request-ID": request_id}
        )
    else:
        # Attendre le résultat Celery directement
        return await _wait_celery_result(task.id, request_id, model)


async def _stream_response(session_id: str, request_id: str, model: str):
    """Génère les events SSE au format OpenAI avec types natifs."""
    redis = await get_redis()
    channel = f"llm:stream:{session_id}"
    pubsub = redis.pubsub()
    
    try:
        await pubsub.subscribe(channel)
        created = int(time.time())
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                
                try:
                    parsed = json.loads(data)
                    
                    if parsed.get("type") == "chunk" and parsed.get("content"):
                        # Format OpenAI streaming avec types natifs
                        chunk = ChatCompletionChunk(
                            id=request_id,
                            object="chat.completion.chunk",
                            created=created,
                            model=model,
                            choices=[
                                ChunkChoice(
                                    index=0,
                                    delta=ChoiceDelta(content=parsed["content"]),
                                    finish_reason=None
                                )
                            ]
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
                    
                    elif parsed.get("type") == "complete":
                        # Final chunk avec finish_reason
                        final_chunk = ChatCompletionChunk(
                            id=request_id,
                            object="chat.completion.chunk",
                            created=created,
                            model=model,
                            choices=[
                                ChunkChoice(
                                    index=0,
                                    delta=ChoiceDelta(),
                                    finish_reason="stop"
                                )
                            ]
                        )
                        yield f"data: {final_chunk.model_dump_json()}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                    
                    elif parsed.get("type") == "error":
                        error_chunk = {
                            "error": {
                                "message": parsed.get("error", "Unknown error"),
                                "type": "server_error"
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                        break
                        
                except json.JSONDecodeError:
                    pass
                    
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def _wait_celery_result(task_id: str, request_id: str, model: str):
    """
    Attendre le résultat Celery et retourner la réponse OpenAI complète.
    
    Retourne directement le dict de la réponse OpenAI pour préserver
    tous les champs (tool_calls, function_call, refusal, etc.)
    """
    from celery.result import AsyncResult
    from app.celery_app import celery
    
    result = AsyncResult(task_id, app=celery)
    
    # Polling async du résultat (timeout depuis config)
    start = time.time()
    
    while not result.ready():
        if time.time() - start > API_TIMEOUT:
            raise HTTPException(504, f"Request timeout after {API_TIMEOUT}s")
        await asyncio.sleep(0.5)
    
    if result.failed():
        raise HTTPException(500, f"Task failed: {result.result}")
    
    task_result = result.result
    
    # Si on a la réponse complète de l'API, l'utiliser directement
    if isinstance(task_result, dict) and "full_response" in task_result:
        response_data = task_result["full_response"]
        # Override l'ID avec notre request_id pour cohérence
        response_data["id"] = request_id
        return response_data
    
    # Fallback: construire une réponse basique
    content = task_result.get("response", "") if isinstance(task_result, dict) else str(task_result)
    usage_data = task_result.get("usage") if isinstance(task_result, dict) else None
    
    return ChatCompletion(
        id=request_id,
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content
                ),
                finish_reason="stop"
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0) if usage_data else 0,
            completion_tokens=usage_data.get("completion_tokens", 0) if usage_data else len(content.split()),
            total_tokens=usage_data.get("total_tokens", 0) if usage_data else len(content.split())
        )
    )


# ============================================================
# AUTRES ENDPOINTS OPENAI
# ============================================================

@router.get("/models")
async def list_models():
    """
    Liste des modèles disponibles via l'API OpenAI.
    Retourne directement les modèles depuis OpenAI.
    """
    try:
        client = get_openai_client()
        models = client.models.list()
        return models
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch models: {str(e)}")


@router.get("/models/{model_id}")
async def get_model(model_id: str) -> Model:
    """
    Récupère les détails d'un modèle spécifique via l'API OpenAI.
    """
    try:
        client = get_openai_client()
        model = client.models.retrieve(model_id)
        return model
    except Exception as e:
        raise HTTPException(404, f"Model not found: {str(e)}")
