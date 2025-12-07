"""
Services RabbitMQ pour LLM Streaming.

Modules:
- connection_pool: Pool de connexions singleton
- llm_worker: Worker LLM indépendant (scalable)
- rabbit_publisher: Publisher pour les sessions
- rabbit_consumer: Consumer SSE pour les sessions
"""
from .connection_pool import get_pool, RabbitConnectionPool
from .rabbit_publisher import RabbitPublisher
from .rabbit_consumer import RabbitConsumer

__all__ = [
    "get_pool",
    "RabbitConnectionPool", 
    "RabbitPublisher",
    "RabbitConsumer"
]
