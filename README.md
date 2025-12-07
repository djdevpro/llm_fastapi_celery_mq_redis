# 🚀 LLM Stream API

> **Scalez votre API LLM** avec Celery + Redis ou RabbitMQ.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-green.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)

## 🎯 Le problème résolu

Votre API LLM lag quand plusieurs utilisateurs envoient des requêtes simultanément ? C'est normal : chaque appel OpenAI prend **10-60 secondes** et bloque un worker HTTP.

**Cette architecture résout le problème** en découplant le traitement :
- L'API retourne **immédiatement** (~100ms)
- Les workers traitent les requêtes **en parallèle**
- Le client reçoit la réponse via **Server-Sent Events**

---

## 🔄 Deux modes disponibles

| Mode | Backend | Avantages |
|------|---------|-----------|
| **Celery** (recommandé) | Redis | Rate limiting, retry auto, priorités, monitoring |
| **RabbitMQ** | RabbitMQ | Legacy, simple |

```bash
# Choisir le mode dans .env
MODE=celery    # ou rabbitmq
```

---

## 📐 Architecture

### Mode Celery + Redis (recommandé) ⚡

```
┌─────────────┐    POST /chat/async    ┌─────────────────┐
│   Client    │ ─────────────────────► │    FastAPI      │
│             │ ◄── task_id, session ─ │   (main_celery) │
└──────┬──────┘                        └────────┬────────┘
       │                                        │
       │                                        ▼
       │ SSE                           ┌─────────────────┐
       │                               │     Redis       │
       │                               │  - Broker       │
       │                               │  - Pub/Sub      │
       │                               │  - Rate limit   │
       │                               └────────┬────────┘
       │                                        │
       │                               ┌────────┴────────┐
       │                               ▼        ▼        ▼
       │                            Celery   Celery   Celery
       │                            Worker   Worker   Worker
       │                               │        │        │
       │ GET /stream/{session_id}      └────────┴────────┘
       │                                        │
       └────────────────────────────────────────┘
                                          chunks SSE
```

### Avantages Celery vs RabbitMQ brut

| Feature | RabbitMQ brut | Celery |
|---------|---------------|--------|
| Retry automatique | ❌ À coder | ✅ `autoretry_for` |
| Backoff exponentiel | ❌ À coder | ✅ `retry_backoff=True` |
| Rate limiting | ❌ À coder | ✅ `rate_limit="100/m"` |
| Priorité des tâches | ❌ À coder | ✅ `queue="high"` |
| Timeout | ❌ À coder | ✅ `task_time_limit=300` |
| Tracking état | ❌ À coder | ✅ `AsyncResult.status` |
| Monitoring | ❌ Rien | ✅ Flower |

---

## ⚙️ Variables d'environnement

```env
# === REQUIS ===
OPENAI_API_KEY=sk-proj-xxxxx

# === MODE (celery ou rabbitmq) ===
MODE=celery

# === REDIS (pour mode celery) ===
REDIS_URL=redis://redis:6379/0

# === RABBITMQ (pour mode rabbitmq, distant CloudAMQP) ===
RABBIT_MQ=amqps://user:pass@coral.rmq.cloudamqp.com/vhost

# === SCALING ===
UVICORN_WORKERS=4       # Workers HTTP
CELERY_CONCURRENCY=4    # Workers Celery (mode celery)
LLM_WORKERS=3           # Workers LLM (mode rabbitmq)
PORT=8007

# === RATE LIMITING ===
LLM_RPM=500             # Requests per minute
LLM_TPM=100000          # Tokens per minute
```

---

## 🚀 Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
# Éditer avec vos clés
```

### 2. Docker Compose (recommandé)

```bash
# Mode Celery (défaut)
docker-compose up -d

# Vérifier les logs
docker-compose logs -f llm-api
```

### 3. Vérification

```bash
# Health check
curl http://localhost:8007/health/full

# Mode Celery :
# {"status":"ok","redis":"connected","celery_workers":"active","openai":"configured"}

# Mode RabbitMQ :
# {"status":"ok","rabbitmq":"connected","openai":"configured"}
```

---

## 📡 API Endpoints

### Mode Celery (`main_celery.py`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/full` | Statut Redis + Celery + OpenAI |
| `POST` | `/chat` | Mode sync (streaming direct) |
| `POST` | `/chat/async` | **Mode async (Celery task)** ⚡ |
| `GET` | `/chat/{task_id}` | Status d'une tâche Celery |
| `GET` | `/stream/{session_id}` | Stream SSE depuis Redis |
| `POST` | `/embeddings` | Batch embeddings async |
| `GET` | `/stats` | Stats queues + workers |

### Mode RabbitMQ (`main.py`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/full` | Statut RabbitMQ + OpenAI |
| `POST` | `/chat` | Mode sync (streaming) |
| `POST` | `/chat/async` | Mode async (RabbitMQ) |
| `GET` | `/stream/{session_id}` | Stream SSE depuis RabbitMQ |
| `GET` | `/stats` | Tâches en attente |

### Exemple : Mode Celery

```bash
# 1. Envoie la requête → retour immédiat
curl -X POST http://localhost:8007/chat/async \
  -H "Content-Type: application/json" \
  -d '{"message": "Explique Docker", "priority": 5}'

# Réponse :
# {
#   "status": "queued",
#   "task_id": "abc-123",
#   "session_id": "xyz-456",
#   "stream_url": "/stream/xyz-456"
# }

# 2. Vérifier le status de la tâche
curl http://localhost:8007/chat/abc-123

# 3. Écouter le stream SSE
curl -N http://localhost:8007/stream/xyz-456
# data: {"type":"status","status":"started"}
# data: {"type":"chunk","content":"Docker"}
# data: {"type":"chunk","content":" est"}
# data: {"type":"complete"}
```

---

## 🧪 Tests

```bash
# Tests mode Celery
pytest tests/test_celery.py -v -s

# Tests mode RabbitMQ
pytest tests/test_concurrent.py -v -s

# Tous les tests
pytest tests/ -v -s
```

### Prérequis pour les tests

```bash
# Mode Celery
docker-compose up -d redis
celery -A celery_app worker --loglevel=info -c 4
uvicorn main_celery:app --port 8007

# Mode RabbitMQ
# RabbitMQ distant (CloudAMQP)
uvicorn main:app --port 8007
```

---

## 📁 Structure du projet

```
llm_fastapi_mq/
├── main.py                 # API FastAPI (mode RabbitMQ)
├── main_celery.py          # API FastAPI (mode Celery) ⚡
├── celery_app.py           # Configuration Celery
├── config.py               # Variables d'environnement
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh           # Lance API + Workers (auto-détecte le mode)
├── chat.html               # Interface web (3 modes)
├── services/
│   ├── connection_pool.py  # Pool connexions RabbitMQ
│   ├── llm_worker.py       # Worker LLM (mode RabbitMQ)
│   ├── rabbit_publisher.py
│   └── rabbit_consumer.py
├── tasks/
│   ├── __init__.py
│   └── llm_tasks.py        # Tâches Celery (rate limiting, retry)
└── tests/
    ├── conftest.py
    ├── test_celery.py      # Tests mode Celery
    └── test_concurrent.py  # Tests mode RabbitMQ
```

---

## 🖥️ Interface Web

```bash
# Ouvrir chat.html dans le navigateur
open chat.html
```

**3 modes disponibles :**
- 🟢 **Celery** — Streaming via Redis pub/sub
- 🔵 **RabbitMQ** — Streaming via RabbitMQ
- ⚡ **Direct** — Streaming HTTP direct

---

## 📊 Scaling

### Mode Celery

```bash
# Plus de workers Celery
CELERY_CONCURRENCY=8

# Ou lancer plusieurs workers
celery -A celery_app worker -c 4 -Q high,default &
celery -A celery_app worker -c 4 -Q low &
```

### Mode RabbitMQ

```bash
# Plus de workers LLM
LLM_WORKERS=10
```

### Configurations recommandées

| Charge | CELERY_CONCURRENCY | UVICORN_WORKERS |
|--------|-------------------|-----------------|
| Dev | 2 | 1 |
| Petit (10 users) | 4 | 2 |
| Moyen (50 users) | 8 | 4 |
| Production (100+) | 16-32 | 4 |

---

## 🐛 Troubleshooting

### Redis non connecté

```bash
# Vérifier que Redis tourne
docker-compose ps redis

# Vérifier l'URL Redis
echo $REDIS_URL
# Doit être redis://redis:6379/0 dans Docker
```

### Celery workers inactifs

```bash
# Vérifier les workers
celery -A celery_app inspect active

# Voir les queues
celery -A celery_app inspect reserved
```

### Erreur caractères Windows

```bash
# Nettoyer les \r du .env
sed -i 's/\r$//' .env
```

### Port déjà utilisé

```bash
# Trouver le processus
netstat -ano | findstr :8007

# Ou changer le port dans .env
PORT=8008
```

---

## 🔜 Roadmap

- [ ] Quotas par utilisateur
- [ ] Budget tracking (cost per user)
- [ ] Multi-provider fallback (OpenAI → Anthropic → Ollama)
- [ ] Celery Beat pour jobs planifiés
- [ ] Flower pour monitoring

---

## 📄 License

MIT

---

<p align="center">
  <b>⭐ Si ce projet vous aide, laissez une étoile !</b>
</p>
