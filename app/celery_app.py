"""
Configuration Celery avec Redis.

Lancer le worker :
    celery -A app.celery_app worker --loglevel=info --concurrency=4
"""
from celery import Celery
from kombu import Queue
from app.config import REDIS_URL

# Celery app
celery = Celery(
    "llm_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.llm_tasks"]
)

# Configuration
celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task settings
    task_track_started=True,
    task_time_limit=300,  # 5 min max par tâche
    task_soft_time_limit=270,  # Warning à 4.5 min
    
    # Results
    result_expires=3600,  # 1h de rétention
    
    # Queues avec priorités
    task_queues=(
        Queue("high", routing_key="high"),
        Queue("default", routing_key="default"),
        Queue("low", routing_key="low"),
    ),
    task_default_queue="default",
    task_default_routing_key="default",
    
    # Rate limiting global (backup)
    task_annotations={
        "app.tasks.llm_tasks.chat_completion": {
            "rate_limit": "100/m"
        }
    },
    
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Concurrency control
    worker_prefetch_multiplier=1,
    
    # Startup retry
    broker_connection_retry_on_startup=True,
)


if __name__ == "__main__":
    celery.start()
