#!/bin/bash
set -e

# ============================================================
# Entrypoint - Lance API + Workers LLM
# ============================================================

# Charge les variables depuis .env si le fichier existe
if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | xargs)
fi

# Valeurs par défaut
UVICORN_WORKERS=${UVICORN_WORKERS:-4}
LLM_WORKERS=${LLM_WORKERS:-3}
PORT=${PORT:-8007}

echo "========================================"
echo "  LLM FastAPI + RabbitMQ"
echo "========================================"
echo "  Uvicorn workers: $UVICORN_WORKERS"
echo "  LLM workers:     $LLM_WORKERS"
echo "  Port:            $PORT"
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

# Lance les workers LLM en background
echo "Démarrage de $LLM_WORKERS worker(s) LLM..."
for i in $(seq 1 $LLM_WORKERS); do
    python -m services.llm_worker &
    echo "  Worker LLM #$i lancé (PID: $!)"
done

# Petit délai pour laisser les workers se connecter à RabbitMQ
sleep 2

# Lance uvicorn au premier plan
echo "Démarrage de l'API (uvicorn)..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers $UVICORN_WORKERS \
    --loop asyncio
