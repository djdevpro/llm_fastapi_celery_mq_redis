"""
Tâches Celery pour les appels LLM.

Features:
- Rate limiting via Celery natif (configuré dans celery_app.py)
- Retry automatique avec backoff exponentiel
- Priorité des tâches via queues
- Streaming via Redis pub/sub
"""
import json
import logging
from typing import Optional
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from openai import OpenAI
import redis

from app.config import (
    OPENAI_API_KEY,
    OPENAI_ORG_ID,
    OPENAI_BASE_URL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_TIMEOUT,
    REDIS_URL,
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
)

logger = logging.getLogger(__name__)

# ============================================================
# CLIENTS (lazy init, une fois par worker)
# ============================================================

_openai_client: Optional[OpenAI] = None
_redis_client: Optional[redis.Redis] = None


def get_openai() -> OpenAI:
    """Lazy init du client OpenAI avec config depuis env."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=OPENAI_API_KEY,
            organization=OPENAI_ORG_ID,
            base_url=OPENAI_BASE_URL,
            timeout=OPENAI_TIMEOUT,
        )
    return _openai_client


def get_redis() -> redis.Redis:
    """Lazy init du client Redis."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


# ============================================================
# TÂCHE PRINCIPALE: CHAT COMPLETION
# ============================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=CELERY_MAX_RETRIES,
    acks_late=True,
    # Rate limit géré par Celery via task_annotations dans celery_app.py
)
def chat_completion(
    self,
    session_id: str,
    completion_params: dict,
) -> dict:
    """
    Tâche Celery pour chat completion.
    
    Accepte TOUS les paramètres OpenAI via completion_params (passés directement à l'API).
    
    Paramètres supportés (tout ce que OpenAI supporte):
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
    
    Publie les chunks en temps réel sur Redis pub/sub.
    Channel: llm:stream:{session_id}
    """
    redis_client = get_redis()
    channel = f"llm:stream:{session_id}"
    
    # Publie le statut "started"
    redis_client.publish(channel, json.dumps({
        "type": "status",
        "status": "started",
        "task_id": self.request.id
    }))
    
    try:
        client = get_openai()
        
        # Appliquer le modèle par défaut si non spécifié
        if "model" not in completion_params:
            completion_params["model"] = OPENAI_DEFAULT_MODEL
        
        # Extraire stream pour la logique interne
        stream = completion_params.get("stream", False)
        
        if stream:
            return _stream_completion(client, completion_params, session_id, channel, redis_client)
        else:
            return _sync_completion(client, completion_params, session_id, channel, redis_client)
            
    except SoftTimeLimitExceeded:
        logger.warning(f"Task {session_id} timeout")
        redis_client.publish(channel, json.dumps({
            "type": "error",
            "error": "Timeout: la requête a pris trop de temps"
        }))
        raise
        
    except Exception as e:
        logger.error(f"Task {session_id} failed: {e}")
        redis_client.publish(channel, json.dumps({
            "type": "error",
            "error": str(e)
        }))
        raise


# ============================================================
# COMPLETION STREAMING
# ============================================================

def _stream_completion(client: OpenAI, completion_params: dict, session_id: str, channel: str, redis_client) -> dict:
    """
    Streaming completion avec publication Redis.
    
    Passe TOUS les paramètres OpenAI directement à l'API.
    """
    model = completion_params.get("model", OPENAI_DEFAULT_MODEL)
    stream = client.chat.completions.create(**completion_params)
    
    full_response = ""
    chunks_count = 0
    
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            chunks_count += 1
            redis_client.publish(channel, json.dumps({
                "type": "chunk",
                "content": content,
                "index": chunks_count
            }))
    
    redis_client.publish(channel, json.dumps({
        "type": "complete",
        "total_chunks": chunks_count
    }))
    
    logger.info(f"Session {session_id}: {len(full_response)} chars, {chunks_count} chunks")
    
    return {
        "session_id": session_id,
        "response": full_response,
        "model": model,
        "chunks": chunks_count,
    }


# ============================================================
# COMPLETION SYNCHRONE
# ============================================================

def _sync_completion(client: OpenAI, completion_params: dict, session_id: str, channel: str, redis_client) -> dict:
    """
    Completion synchrone.
    
    Passe TOUS les paramètres OpenAI directement à l'API.
    """
    model = completion_params.get("model", OPENAI_DEFAULT_MODEL)
    response = client.chat.completions.create(**completion_params)
    
    content = response.choices[0].message.content
    
    redis_client.publish(channel, json.dumps({
        "type": "complete",
        "content": content
    }))
    
    # Construire usage si disponible
    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        # Ajouter les nouveaux champs si présents (reasoning tokens, cached, etc.)
        if hasattr(response.usage, "completion_tokens_details") and response.usage.completion_tokens_details:
            usage["completion_tokens_details"] = response.usage.completion_tokens_details.model_dump()
        if hasattr(response.usage, "prompt_tokens_details") and response.usage.prompt_tokens_details:
            usage["prompt_tokens_details"] = response.usage.prompt_tokens_details.model_dump()
    
    logger.info(f"Session {session_id}: {len(content)} chars, tokens: {usage}")
    
    return {
        "session_id": session_id,
        "response": content,
        "model": model,
        "usage": usage,
        # Retourner la réponse complète pour accès aux métadonnées (tool_calls, etc.)
        "full_response": response.model_dump()
    }


# ============================================================
# TÂCHE: EMBEDDINGS BATCH
# ============================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    max_retries=CELERY_MAX_RETRIES,
    # Rate limit géré par Celery via task_annotations dans celery_app.py
)
def batch_embeddings(
    self,
    texts: list[str],
    model: str = "text-embedding-3-small",
) -> dict:
    """
    Génère des embeddings en batch.
    
    Args:
        texts: Liste de textes à encoder (max 100)
        model: Modèle d'embedding (text-embedding-3-small, text-embedding-3-large, etc.)
    
    Returns:
        dict avec embeddings, model, count, dimensions
    """
    client = get_openai()
    response = client.embeddings.create(model=model, input=texts)
    embeddings = [item.embedding for item in response.data]
    
    logger.info(f"Embeddings: {len(embeddings)} texts, model: {model}")
    
    return {
        "embeddings": embeddings,
        "model": model,
        "count": len(embeddings),
        "dimensions": len(embeddings[0]) if embeddings else 0,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    }
