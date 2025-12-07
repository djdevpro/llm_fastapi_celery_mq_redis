#!/bin/bash
set -e

# ============================================================
# Entrypoint - Lance API + Workers (Celery ou RabbitMQ)
# ============================================================

# Charge les variables depuis .env (nettoie \r Windows + commentaires inline)
if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | sed 's/#.*//' | tr -d '\r' | xargs)
fi

# Nettoie les variables (peuvent avoir des \r sous Windows)
MODE=$(echo "${MODE:-celery}" | tr -d '\r')
UVICORN_WORKERS=$(echo "${UVICORN_WORKERS:-4}" | tr -d '\r')
LLM_WORKERS=$(echo "${LLM_WORKERS:-3}" | tr -d '\r')
CELERY_CONCURRENCY=$(echo "${CELERY_CONCURRENCY:-4}" | tr -d '\r')
PORT=$(echo "${PORT:-8007}" | tr -d '\r')

echo "========================================"
echo "  LLM FastAPI - Mode: $MODE"
echo "========================================"
echo "  Port:            $PORT"
echo "  Uvicorn workers: $UVICORN_WORKERS"
if [ "$MODE" = "celery" ]; then
    echo "  Celery workers:  $CELERY_CONCURRENCY"
else
    echo "  LLM workers:     $LLM_WORKERS"
fi
echo "========================================"

# Fonction pour cleanup propre
cleanup() {
    echo "Arrêt des workers..."
    kill $(jobs -p) 2>/dev/null
    wait
    echo "Terminé."
    exit 0
}
trap cleanup SIGTERM SIGINT

# ============================================================
# MODE CELERY
# ============================================================
if [ "$MODE" = "celery" ]; then
    echo "Mode: Celery + Redis"
    
    # Vérifie Redis
    echo "Vérification Redis..."
    python -c "import redis; r = redis.from_url('${REDIS_URL:-redis://localhost:6379/0}'); r.ping()" || {
        echo "ERREUR: Redis non disponible"
        exit 1
    }
    echo "Redis OK"
    
    # Lance Celery worker en background
    echo "Démarrage Celery worker (concurrency: $CELERY_CONCURRENCY)..."
    celery -A celery_app worker \
        --loglevel=info \
        --concurrency=$CELERY_CONCURRENCY \
        --queues=high,default,low \
        &
    CELERY_PID=$!
    echo "  Celery worker lancé (PID: $CELERY_PID)"
    
    # Attend que Celery soit prêt
    sleep 3
    
    # Lance uvicorn avec main_celery
    echo "Démarrage de l'API (main_celery)..."
    exec uvicorn main_celery:app \
        --host 0.0.0.0 \
        --port $PORT \
        --workers $UVICORN_WORKERS \
        --loop asyncio

# ============================================================
# MODE RABBITMQ (legacy)
# ============================================================
elif [ "$MODE" = "rabbitmq" ]; then
    echo "Mode: RabbitMQ (legacy)"
    
    # Lance les workers LLM en background
    echo "Démarrage de $LLM_WORKERS worker(s) LLM..."
    for i in $(seq 1 $LLM_WORKERS); do
        python -m services.llm_worker &
        echo "  Worker LLM #$i lancé (PID: $!)"
    done
    
    # Petit délai pour laisser les workers se connecter à RabbitMQ
    sleep 2
    
    # Lance uvicorn avec main (legacy)
    echo "Démarrage de l'API (main)..."
    exec uvicorn main:app \
        --host 0.0.0.0 \
        --port $PORT \
        --workers $UVICORN_WORKERS \
        --loop asyncio

# ============================================================
# MODE INCONNU
# ============================================================
else
    echo "ERREUR: MODE inconnu '$MODE'"
    echo "Valeurs acceptées: celery, rabbitmq"
    exit 1
fi
