"""
Pool de connexions RabbitMQ - Singleton réutilisable.
Évite de recréer une connexion à chaque requête (gain ~100ms/requête).
"""
import pika
import logging
from threading import Lock
from contextlib import contextmanager
from config import RABBIT_MQ_URL

logger = logging.getLogger("rabbit-pool")


class RabbitConnectionPool:
    """
    Pool singleton pour réutiliser les connexions RabbitMQ.
    Thread-safe avec un lock pour l'accès concurrent.
    """
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._connection = None
        self._channel_lock = Lock()
        self._initialized = True
        logger.info("RabbitMQ Pool initialisé")
    
    def _get_connection(self) -> pika.BlockingConnection:
        """Retourne ou crée la connexion partagée."""
        if self._connection is None or self._connection.is_closed:
            if not RABBIT_MQ_URL:
                raise ValueError("RABBIT_MQ non configuré")
            
            params = pika.URLParameters(RABBIT_MQ_URL)
            params.heartbeat = 600  # Keep-alive 10 min
            params.blocked_connection_timeout = 300
            self._connection = pika.BlockingConnection(params)
            logger.info("Nouvelle connexion RabbitMQ établie")
        
        return self._connection
    
    @contextmanager
    def channel(self):
        """
        Context manager pour obtenir un channel thread-safe.
        
        Usage:
            pool = RabbitConnectionPool()
            with pool.channel() as ch:
                ch.basic_publish(...)
        """
        with self._channel_lock:
            conn = self._get_connection()
            ch = conn.channel()
            try:
                yield ch
            finally:
                if ch.is_open:
                    ch.close()
    
    def publish(self, queue: str, message: bytes, declare: bool = True):
        """
        Publie un message de manière thread-safe.
        
        Args:
            queue: Nom de la queue
            message: Corps du message (bytes)
            declare: Déclarer la queue si elle n'existe pas
        """
        with self.channel() as ch:
            if declare:
                ch.queue_declare(
                    queue=queue,
                    durable=True,  # Survit au redémarrage
                    arguments={"x-message-ttl": 300000}  # TTL 5 min
                )
            
            ch.basic_publish(
                exchange="",
                routing_key=queue,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistant
                    content_type="application/json"
                )
            )
    
    def close(self):
        """Ferme proprement la connexion."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("Connexion RabbitMQ fermée")


# Singleton global
_pool = None

def get_pool() -> RabbitConnectionPool:
    """Retourne le pool singleton."""
    global _pool
    if _pool is None:
        _pool = RabbitConnectionPool()
    return _pool
