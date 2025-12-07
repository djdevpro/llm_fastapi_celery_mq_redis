#!/bin/bash
set -e

# ============================================================
# Entrypoint Worker - Lance Celery uniquement
# ============================================================

echo "========================================"
echo "  LLM Worker - Celery"
echo "========================================"
echo "  Concurrency:     ${CELERY_CONCURRENCY:-4}"
echo "  Queues:          ${CELERY_QUEUES:-high,default,low}"
echo "  Loglevel:        ${CELERY_LOGLEVEL:-info}"
echo "  Redis:           ${REDIS_URL:-redis://localhost:6379/0}"
echo "========================================"

exec celery -A app.celery_app worker \
    --loglevel=${CELERY_LOGLEVEL:-info} \
    --concurrency=${CELERY_CONCURRENCY:-4} \
    --queues=${CELERY_QUEUES:-high,default,low} \
    --hostname=worker@%h
