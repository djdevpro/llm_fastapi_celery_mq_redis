"""
Configuration Celery avec Redis.

Lancer le worker :
    celery -A app.celery_app worker --loglevel=info --concurrency=4
    
Toute la config est pilotée via les variables d'environnement (voir config.py)
"""
from celery import Celery
from kombu import Queue
from app.config import (
    BROKER_URL,
    RESULT_BACKEND,
    CELERY_RATE_LIMIT,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_RESULT_EXPIRES,
    CELERY_PREFETCH_MULTIPLIER,
    CELERY_QUEUES,
)

# Celery app
celery = Celery(
    "llm_tasks",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.tasks.llm_tasks"]
)

print(f"[Celery] Broker: {BROKER_URL[:30]}...")
print(f"[Celery] Rate limit: {CELERY_RATE_LIMIT}")
print(f"[Celery] Queues: {CELERY_QUEUES}")

# Parser les queues depuis la config
queue_names = [q.strip() for q in CELERY_QUEUES.split(",") if q.strip()]
task_queues = tuple(Queue(name, routing_key=name) for name in queue_names)

# Configuration
celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task settings (depuis env)
    task_track_started=True,
    task_time_limit=CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
    
    # Results
    result_expires=CELERY_RESULT_EXPIRES,
    
    # Queues avec priorités (depuis env)
    task_queues=task_queues,
    task_default_queue="default" if "default" in queue_names else queue_names[0],
    task_default_routing_key="default" if "default" in queue_names else queue_names[0],
    
    # Rate limiting natif Celery (depuis env)
    task_annotations={
        "app.tasks.llm_tasks.chat_completion": {
            "rate_limit": CELERY_RATE_LIMIT
        },
        "app.tasks.llm_tasks.batch_embeddings": {
            "rate_limit": CELERY_RATE_LIMIT
        }
    },
    
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Concurrency control (depuis env)
    worker_prefetch_multiplier=CELERY_PREFETCH_MULTIPLIER,
    
    # Startup retry
    broker_connection_retry_on_startup=True,
)


if __name__ == "__main__":
    celery.start()
