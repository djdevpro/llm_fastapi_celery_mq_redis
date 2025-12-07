import json
import pika
from config import RABBIT_MQ_URL


class RabbitPublisher:
    """Publisher RabbitMQ pour envoyer les chunks LLM."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.queue = f"llm_session_{session_id}"
        self._connection = None
        self._channel = None
    
    def connect(self):
        """Établit la connexion à RabbitMQ."""
        if not RABBIT_MQ_URL:
            raise ValueError("RABBIT_MQ non défini")
        
        params = pika.URLParameters(RABBIT_MQ_URL)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        
        # Queue par session, auto-delete quand plus de consumers
        self._channel.queue_declare(
            queue=self.queue,
            durable=False,
            auto_delete=True,
            arguments={"x-expires": 60000}  # Expire après 60s d'inactivité
        )
    
    def publish(self, message: dict):
        """Publie un message dans la queue de session."""
        if not self._channel:
            raise RuntimeError("Non connecté à RabbitMQ")
        
        self._channel.basic_publish(
            exchange="",
            routing_key=self.queue,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=1  # Non persistant (transient)
            )
        )
    
    def close(self):
        """Ferme la connexion."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.close()
