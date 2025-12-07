"""Configuration de l'application."""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Redis (Celery broker + cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()

# Rate Limiting LLM
LLM_RPM = int(os.getenv("LLM_RPM", "500"))  # Requests per minute
LLM_TPM = int(os.getenv("LLM_TPM", "100000"))  # Tokens per minute

# Legacy RabbitMQ (optionnel)
RABBIT_MQ_URL = os.getenv("RABBIT_MQ", "").strip()
DEFAULT_QUEUE = "llm_responses"
