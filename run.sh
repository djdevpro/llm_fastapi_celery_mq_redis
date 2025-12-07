#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# LLM Stream + RabbitMQ - Script de gestion
# ═══════════════════════════════════════════════════════════════

set -e

IMAGE_NAME="llm-fastapi-mq"
CONTAINER_NAME="llm-mq-poc"
PORT="8007"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

build() {
    log_info "Build de l'image Docker..."
    docker build -t $IMAGE_NAME .
    log_success "Image $IMAGE_NAME créée"
}

start() {
    check_env
    
    # Stop si déjà running
    if docker ps -q -f name=$CONTAINER_NAME | grep -q .; then
        log_warn "Container déjà en cours, restart..."
        docker rm -f $CONTAINER_NAME > /dev/null 2>&1
    fi
    
    # Build
    build
    
    # Run
    log_info "Lancement du container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p $PORT:$PORT \
        --env-file .env \
        --restart unless-stopped \
        $IMAGE_NAME
    
    sleep 2
    
    # Health check
    if curl -s http://localhost:$PORT/health | grep -q "ok"; then
        log_success "Container démarré sur http://localhost:$PORT"
        echo ""
        log_info "Endpoints disponibles:"
        echo "  • GET  /health              - Health check"
        echo "  • GET  /test                - Test OpenAI"
        echo "  • POST /chat                - Chat streaming"
        echo "  • GET  /stream/{session_id} - SSE RabbitMQ"
        echo ""
        log_info "Interface web: ouvrir chat.html"
    else
        log_error "Le container ne répond pas"
        docker logs $CONTAINER_NAME --tail 20
        exit 1
    fi
}

stop() {
    log_info "Arrêt du container..."
    docker rm -f $CONTAINER_NAME > /dev/null 2>&1 || true
    log_success "Container arrêté"
}

restart() {
    stop
    start
}

logs() {
    docker logs $CONTAINER_NAME -f --tail 50
}

shell() {
    log_info "Connexion au container..."
    docker exec -it $CONTAINER_NAME sh
}

status() {
    if docker ps -q -f name=$CONTAINER_NAME | grep -q .; then
        log_success "Container en cours d'exécution"
        docker ps -f name=$CONTAINER_NAME --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    else
        log_warn "Container non démarré"
    fi
}

test_api() {
    log_info "Test des endpoints..."
    echo ""
    
    # Health
    echo -n "  /health     : "
    if curl -s http://localhost:$PORT/health | grep -q "ok"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    
    # Test OpenAI
    echo -n "  /test       : "
    RESULT=$(curl -s http://localhost:$PORT/test)
    if echo "$RESULT" | grep -q "OK:"; then
        echo -e "${GREEN}OK${NC} - $(echo $RESULT | head -c 50)..."
    else
        echo -e "${RED}FAIL${NC} - $RESULT"
    fi
    
    # Chat
    echo -n "  /chat       : "
    RESULT=$(curl -s -X POST http://localhost:$PORT/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "Dis bonjour en 3 mots"}' \
        --max-time 30)
    if [ -n "$RESULT" ] && ! echo "$RESULT" | grep -q "ERROR"; then
        echo -e "${GREEN}OK${NC} - $(echo $RESULT | head -c 50)..."
    else
        echo -e "${RED}FAIL${NC}"
    fi
    
    echo ""
}

clean() {
    log_info "Nettoyage..."
    docker rm -f $CONTAINER_NAME > /dev/null 2>&1 || true
    docker rmi $IMAGE_NAME > /dev/null 2>&1 || true
    log_success "Nettoyage terminé"
}

usage() {
    echo ""
    echo "Usage: ./run.sh <command>"
    echo ""
    echo "Commands:"
    echo "  start     Build et lance le container"
    echo "  stop      Arrête le container"
    echo "  restart   Redémarre le container"
    echo "  logs      Affiche les logs (follow)"
    echo "  shell     Ouvre un shell dans le container"
    echo "  status    Affiche le statut du container"
    echo "  test      Test les endpoints API"
    echo "  build     Build l'image Docker uniquement"
    echo "  clean     Supprime le container et l'image"
    echo ""
}

# ───────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    logs)    logs ;;
    shell)   shell ;;
    status)  status ;;
    test)    test_api ;;
    build)   build ;;
    clean)   clean ;;
    *)       usage ;;
esac
