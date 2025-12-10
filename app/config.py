"""
Configuration de l'application.

Toutes les variables sont configurables via .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# OPENAI
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_ORG_ID = os.getenv("OPENAI_ORG_ID", "").strip() or None
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None  # Pour proxy/Azure
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini").strip()
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "600"))  # 10 min par défaut (o1/o3 peuvent être longs)

# ============================================================
# REDIS / BROKER
# ============================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
BROKER_URL = os.getenv("BROKER_URL", REDIS_URL).strip()
RESULT_BACKEND = os.getenv("RESULT_BACKEND", REDIS_URL).strip()

# ============================================================
# CELERY - RATE LIMITING (natif Celery)
# ============================================================
# Format: "100/m" (par minute), "10/s" (par seconde), "1000/h" (par heure)
CELERY_RATE_LIMIT = os.getenv("CELERY_RATE_LIMIT", "100/m").strip()

# ============================================================
# CELERY - TASK SETTINGS
# ============================================================
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "900"))  # 15 min max (o1/o3 peuvent être longs)
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "870"))  # Warning 14.5 min
CELERY_RESULT_EXPIRES = int(os.getenv("CELERY_RESULT_EXPIRES", "3600"))  # 1h rétention
CELERY_MAX_RETRIES = int(os.getenv("CELERY_MAX_RETRIES", "3"))
CELERY_RETRY_BACKOFF_MAX = int(os.getenv("CELERY_RETRY_BACKOFF_MAX", "60"))  # secondes

# ============================================================
# CELERY - WORKER SETTINGS
# ============================================================
CELERY_CONCURRENCY = int(os.getenv("CELERY_CONCURRENCY", "4"))
CELERY_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_PREFETCH_MULTIPLIER", "1"))
CELERY_QUEUES = os.getenv("CELERY_QUEUES", "high,default,low").strip()
CELERY_LOGLEVEL = os.getenv("CELERY_LOGLEVEL", "info").strip()

# ============================================================
# API SETTINGS
# ============================================================
PORT = int(os.getenv("PORT", "8007"))
UVICORN_WORKERS = int(os.getenv("UVICORN_WORKERS", "4"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "900"))  # Timeout proxy (doit être >= CELERY_TASK_TIME_LIMIT)

# ============================================================
# UI
# ============================================================
UI_PORT = int(os.getenv("UI_PORT", "3000"))
API_URL = os.getenv("API_URL", f"http://localhost:{PORT}").strip()

# ============================================================
# MONITORING
# ============================================================
FLOWER_PORT = int(os.getenv("FLOWER_PORT", "5555"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip()
