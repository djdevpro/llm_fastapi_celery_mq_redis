"""
Worker LLM indépendant - Traite les requêtes depuis RabbitMQ.
Lance ce script séparément pour scaler horizontalement.

Usage:
    python -m services.llm_worker
    # Ou avec plusieurs instances :
    python -m services.llm_worker &
    python -m services.llm_worker &
"""
import json
import pika
import logging
import signal
import sys
from openai import OpenAI
from config import RABBIT_MQ_URL, OPENAI_API_KEY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("llm-worker")

# Queues
TASK_QUEUE = "llm_tasks"  # Reçoit les tâches
PREFETCH_COUNT = 1  # Traite 1 tâche à la fois (équilibrage de charge)


class LLMWorker:
    """
    Worker qui consomme les tâches LLM depuis RabbitMQ.
    Publie les chunks de réponse dans la queue de session.
    """
    
    def __init__(self):
        self._connection = None
        self._channel = None
        self._openai = OpenAI(api_key=OPENAI_API_KEY)
        self._running = True
        
        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Arrêt propre du worker."""
        logger.info("Arrêt du worker...")
        self._running = False
        if self._channel:
            self._channel.stop_consuming()
    
    def connect(self):
        """Établit la connexion à RabbitMQ."""
        params = pika.URLParameters(RABBIT_MQ_URL)
        params.heartbeat = 600
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        
        # Queue de tâches durable
        self._channel.queue_declare(
            queue=TASK_QUEUE,
            durable=True,
            arguments={"x-message-ttl": 300000}  # TTL 5 min
        )
        
        # QoS : traite 1 message à la fois
        self._channel.basic_qos(prefetch_count=PREFETCH_COUNT)
        
        logger.info(f"Worker connecté, écoute sur '{TASK_QUEUE}'")
    
    def _process_task(self, ch, method, properties, body):
        """
        Traite une tâche LLM.
        
        Format attendu:
        {
            "session_id": "uuid",
            "message": "Question utilisateur",
            "model": "gpt-4o-mini" (optionnel)
        }
        """
        try:
            task = json.loads(body)
            session_id = task["session_id"]
            message = task["message"]
            model = task.get("model", "gpt-4o-mini")
            
            response_queue = f"llm_session_{session_id}"
            
            logger.info(f"Traitement session {session_id[:8]}...")
            
            # Déclare la queue de réponse
            ch.queue_declare(
                queue=response_queue,
                durable=False,
                auto_delete=True,
                arguments={"x-expires": 60000}
            )
            
            # Stream OpenAI
            stream = self._openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Tu es un assistant utile et concis."},
                    {"role": "user", "content": message}
                ],
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_response += content
                    ch.basic_publish(
                        exchange="",
                        routing_key=response_queue,
                        body=json.dumps({"type": "chunk", "chunk": content})
                    )
            
            # Signal de fin
            ch.basic_publish(
                exchange="",
                routing_key=response_queue,
                body=json.dumps({"type": "complete"})
            )
            
            # Acknowledge la tâche traitée
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"Session {session_id[:8]} terminée ({len(full_response)} chars)")
            
        except Exception as e:
            logger.error(f"Erreur traitement: {e}", exc_info=True)
            
            # Publie l'erreur si on a le session_id
            if 'session_id' in locals():
                try:
                    ch.basic_publish(
                        exchange="",
                        routing_key=f"llm_session_{session_id}",
                        body=json.dumps({"type": "error", "error": str(e)})
                    )
                except:
                    pass
            
            # Reject sans requeue (évite les boucles infinies)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def run(self):
        """Lance le worker en boucle."""
        while self._running:
            try:
                self.connect()
                self._channel.basic_consume(
                    queue=TASK_QUEUE,
                    on_message_callback=self._process_task
                )
                logger.info("Worker démarré, en attente de tâches...")
                self._channel.start_consuming()
                
            except pika.exceptions.AMQPConnectionError as e:
                if self._running:
                    logger.warning(f"Connexion perdue, reconnexion dans 5s: {e}")
                    import time
                    time.sleep(5)
            except Exception as e:
                logger.error(f"Erreur worker: {e}", exc_info=True)
                if self._running:
                    import time
                    time.sleep(5)
        
        if self._connection and not self._connection.is_closed:
            self._connection.close()
        
        logger.info("Worker arrêté proprement")


if __name__ == "__main__":
    worker = LLMWorker()
    worker.run()
