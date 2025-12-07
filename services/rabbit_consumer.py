import json
import asyncio
import pika
from config import RABBIT_MQ_URL


class RabbitConsumer:
    """Consumer RabbitMQ pour recevoir les chunks d'une session."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.queue = f"llm_session_{session_id}"
        self._connection = None
        self._channel = None
    
    def connect(self):
        """Établit la connexion et déclare la queue."""
        if not RABBIT_MQ_URL:
            raise ValueError("RABBIT_MQ non défini")
        
        params = pika.URLParameters(RABBIT_MQ_URL)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        
        # Même déclaration que le publisher
        self._channel.queue_declare(
            queue=self.queue,
            durable=False,
            auto_delete=True,
            arguments={"x-expires": 60000}
        )
    
    async def consume_session(self):
        """Génère les chunks jusqu'au message 'complete'."""
        if not self._channel:
            self.connect()
        
        timeout_count = 0
        max_timeout = 300  # 30 secondes max d'attente (300 * 0.1s)
        
        while timeout_count < max_timeout:
            method, properties, body = self._channel.basic_get(
                queue=self.queue,
                auto_ack=True
            )
            
            if method:
                timeout_count = 0  # Reset timeout
                message = json.loads(body)
                
                if message.get("type") == "chunk":
                    yield message.get("chunk", "")
                elif message.get("type") == "complete":
                    break
                elif message.get("type") == "error":
                    yield f"[ERROR: {message.get('error')}]"
                    break
            else:
                timeout_count += 1
                await asyncio.sleep(0.1)
    
    def close(self):
        """Ferme la connexion."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.close()
