"""Configuration de l'application."""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Celery Broker (redis ou rabbitmq)
# BROKER=redis → redis://localhost:6379/0
# BROKER=rabbitmq → amqp://guest:guest@localhost:5672/
BROKER = os.getenv("BROKER", "redis").strip().lower()

if BROKER == "rabbitmq":
    BROKER_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/").strip()
    RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()  # Results toujours en Redis
else:
    BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    RESULT_BACKEND = BROKER_URL

# Redis pour pub/sub streaming (toujours Redis)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()

# Rate Limiting LLM
LLM_RPM = int(os.getenv("LLM_RPM", "500"))  # Requests per minute
LLM_TPM = int(os.getenv("LLM_TPM", "100000"))  # Tokens per minute
