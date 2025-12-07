#!/bin/bash
set -e

# ============================================================
# Entrypoint API - Lance FastAPI uniquement
# ============================================================

echo "========================================"
echo "  LLM API - FastAPI"
echo "========================================"
echo "  Port:            ${PORT:-8007}"
echo "  Workers:         ${UVICORN_WORKERS:-4}"
echo "  Redis:           ${REDIS_URL:-redis://localhost:6379/0}"
echo "========================================"

exec uvicorn app.api.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8007} \
    --workers ${UVICORN_WORKERS:-4}
