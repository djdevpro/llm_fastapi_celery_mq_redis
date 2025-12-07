"""Celery tasks package."""
from app.tasks.llm_tasks import chat_completion, batch_embeddings

__all__ = ["chat_completion", "batch_embeddings"]
