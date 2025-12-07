import os
from dotenv import load_dotenv

load_dotenv()

RABBIT_MQ_URL = os.getenv("RABBIT_MQ", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Queue par défaut
DEFAULT_QUEUE = "llm_responses"
