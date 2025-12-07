"""
Tâches Celery pour les appels LLM.

Features:
- Rate limiting intelligent (token bucket)
- Retry automatique avec backoff
- Priorité des tâches
- Streaming via Redis pub/sub
"""
import json
import logging
import time
from typing import Optional
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from openai import OpenAI
import redis

from app.config import OPENAI_API_KEY, REDIS_URL, LLM_RPM

logger = logging.getLogger(__name__)

# Clients (initialisés une fois par worker)
_openai_client: Optional[OpenAI] = None
_redis_client: Optional[redis.Redis] = None


def get_openai():
    """Lazy init du client OpenAI."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def get_redis():
    """Lazy init du client Redis."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


class RateLimiter:
    """Token bucket rate limiter avec Redis."""
    
    def __init__(self, key: str, rate: int, period: int = 60):
        self.key = f"ratelimit:{key}"
        self.rate = rate
        self.period = period
        self.redis = get_redis()
    
    def acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """Acquiert des tokens. Bloque si nécessaire."""
        start = time.time()
        
        while time.time() - start < timeout:
            script = """
            local key = KEYS[1]
            local rate = tonumber(ARGV[1])
            local period = tonumber(ARGV[2])
            local requested = tonumber(ARGV[3])
            local now = tonumber(ARGV[4])
            
            local bucket = redis.call('HGETALL', key)
            local tokens = rate
            local last_update = now
            
            if #bucket > 0 then
                tokens = tonumber(bucket[2]) or rate
                last_update = tonumber(bucket[4]) or now
            end
            
            local elapsed = now - last_update
            local refill = (elapsed / period) * rate
            tokens = math.min(rate, tokens + refill)
            
            if tokens >= requested then
                tokens = tokens - requested
                redis.call('HSET', key, 'tokens', tokens, 'last_update', now)
                redis.call('EXPIRE', key, period * 2)
                return 1
            end
            
            return 0
            """
            
            result = self.redis.eval(
                script, 1, self.key,
                self.rate, self.period, tokens, time.time()
            )
            
            if result == 1:
                return True
            
            time.sleep(0.1)
        
        return False


# Rate limiter global pour OpenAI
_openai_limiter = None


def get_limiter():
    """Lazy init du rate limiter."""
    global _openai_limiter
    if _openai_limiter is None:
        _openai_limiter = RateLimiter("openai", rate=LLM_RPM, period=60)
    return _openai_limiter


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def chat_completion(
    self,
    session_id: str,
    message: str,
    model: str = "gpt-4o-mini",
    system_prompt: str = "Tu es un assistant utile et concis.",
    stream: bool = True,
    user_id: Optional[str] = None,
) -> dict:
    """
    Tâche Celery pour chat completion.
    
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
        # Acquire rate limit
        limiter = get_limiter()
        if not limiter.acquire(tokens=1, timeout=30):
            raise Exception("Rate limit timeout - trop de requêtes")
        
        client = get_openai()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        if stream:
            return _stream_completion(client, messages, model, session_id, channel, redis_client)
        else:
            return _sync_completion(client, messages, model, session_id, channel, redis_client)
            
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


def _stream_completion(client, messages, model, session_id, channel, redis_client) -> dict:
    """Streaming completion avec publication Redis."""
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True
    )
    
    full_response = ""
    chunks_count = 0
    
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        if content:
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
    
    logger.info(f"Session {session_id}: {len(full_response)} chars")
    
    return {
        "session_id": session_id,
        "response": full_response,
        "model": model,
        "chunks": chunks_count,
    }


def _sync_completion(client, messages, model, session_id, channel, redis_client) -> dict:
    """Completion synchrone."""
    response = client.chat.completions.create(model=model, messages=messages)
    content = response.choices[0].message.content
    
    redis_client.publish(channel, json.dumps({
        "type": "complete",
        "content": content
    }))
    
    return {
        "session_id": session_id,
        "response": content,
        "model": model,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
    }


@shared_task(bind=True, max_retries=1)
def batch_embeddings(
    self,
    texts: list[str],
    model: str = "text-embedding-3-small",
    user_id: Optional[str] = None,
) -> dict:
    """Génère des embeddings en batch."""
    limiter = get_limiter()
    if not limiter.acquire(tokens=1, timeout=60):
        raise Exception("Rate limit timeout")
    
    client = get_openai()
    response = client.embeddings.create(model=model, input=texts)
    embeddings = [item.embedding for item in response.data]
    
    return {
        "embeddings": embeddings,
        "model": model,
        "count": len(embeddings),
        "dimensions": len(embeddings[0]) if embeddings else 0
    }
