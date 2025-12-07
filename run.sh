#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# LLM API - Script de gestion (Docker Compose)
# ═══════════════════════════════════════════════════════════════

set -e

DOCKER_DIR="docker"
PORT="${PORT:-8007}"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ───────────────────────────────────────────────────────────────
# Fonctions
# ───────────────────────────────────────────────────────────────

check_env() {
    if [ ! -f ".env" ]; then
        log_error "Fichier .env manquant"
        log_info "Copie .env.example vers .env et configure les variables"
        exit 1
    fi
}

dc() {
    docker-compose -f $DOCKER_DIR/docker-compose.yml "$@"
}

build() {
    log_info "Build des images Docker..."
    dc build
    log_success "Images créées"
}

start() {
    check_env
    log_info "Démarrage des services..."
    dc up -d
    
    sleep 3
    
    if curl -s http://localhost:$PORT/health | grep -q "ok"; then
        log_success "Services démarrés"
        echo ""
        log_info "Endpoints: http://localhost:$PORT"
        echo "  • GET  /health"
        echo "  • POST /chat"
        echo "  • POST /chat/async"
        echo "  • GET  /stream/{session_id}"
        echo ""
        log_info "Interface web: open chat.html"
    else
        log_error "L'API ne répond pas"
        dc logs --tail 20 api
        exit 1
    fi
}

stop() {
    log_info "Arrêt des services..."
    dc down
    log_success "Services arrêtés"
}

restart() {
    stop
    start
}

logs() {
    dc logs -f --tail 50 "$@"
}

shell_api() {
    log_info "Connexion à l'API..."
    dc exec api sh
}

shell_worker() {
    log_info "Connexion au worker..."
    dc exec worker sh
}

status() {
    dc ps
}

scale() {
    if [ -z "$2" ]; then
        log_error "Usage: ./run.sh scale <nombre>"
        exit 1
    fi
    log_info "Scaling workers à $2..."
    dc up -d --scale worker=$2
    log_success "$2 workers actifs"
}

monitoring() {
    log_info "Démarrage avec monitoring Flower..."
    dc --profile monitoring up -d
    log_success "Flower disponible sur http://localhost:5555"
}

test_api() {
    log_info "Test des endpoints..."
    echo ""
    
    echo -n "  /health       : "
    if curl -s http://localhost:$PORT/health | grep -q "ok"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    
    echo -n "  /health/full  : "
    RESULT=$(curl -s http://localhost:$PORT/health/full)
    if echo "$RESULT" | grep -q "redis.*connected"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}DEGRADED${NC} - $RESULT"
    fi
    
    echo -n "  /chat (sync)  : "
    RESULT=$(curl -s -X POST http://localhost:$PORT/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "Dis OK"}' \
        --max-time 30)
    if [ -n "$RESULT" ] && ! echo "$RESULT" | grep -q "ERROR"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    
    echo -n "  /chat/async   : "
    RESULT=$(curl -s -X POST http://localhost:$PORT/chat/async \
        -H "Content-Type: application/json" \
        -d '{"message": "Test"}')
    if echo "$RESULT" | grep -q "queued"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    
    echo ""
}

clean() {
    log_info "Nettoyage complet..."
    dc down -v --rmi all 2>/dev/null || true
    log_success "Nettoyage terminé"
}

usage() {
    echo ""
    echo "Usage: ./run.sh <command>"
    echo ""
    echo "Commands:"
    echo "  start         Démarre API + Worker + Redis"
    echo "  stop          Arrête tous les services"
    echo "  restart       Redémarre les services"
    echo "  logs [svc]    Affiche les logs (api, worker, redis)"
    echo "  shell-api     Shell dans le container API"
    echo "  shell-worker  Shell dans le container Worker"
    echo "  status        Affiche le statut des services"
    echo "  scale <n>     Scale les workers Celery"
    echo "  monitoring    Démarre avec Flower (port 5555)"
    echo "  test          Test les endpoints API"
    echo "  build         Build les images"
    echo "  clean         Supprime tout (containers, volumes, images)"
    echo ""
}

# ───────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────

case "${1:-}" in
    start)        start ;;
    stop)         stop ;;
    restart)      restart ;;
    logs)         shift; logs "$@" ;;
    shell-api)    shell_api ;;
    shell-worker) shell_worker ;;
    status)       status ;;
    scale)        scale "$@" ;;
    monitoring)   monitoring ;;
    test)         test_api ;;
    build)        build ;;
    clean)        clean ;;
    *)            usage ;;
esac
