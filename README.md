# 🚀 LLM Stream API

> **API LLM scalable** avec Celery + Redis.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-green.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)

---

## 📁 Structure du projet

```
llm_fastapi_mq/
├── app/                        # Code source
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py             # FastAPI application
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── llm_tasks.py        # Tâches Celery
│   ├── services/               # Services legacy (RabbitMQ)
│   ├── __init__.py
│   ├── config.py               # Configuration
│   └── celery_app.py           # Configuration Celery
│
├── docker/                     # Fichiers Docker
│   ├── Dockerfile.api          # Image API
│   ├── Dockerfile.worker       # Image Worker Celery
│   ├── entrypoint-api.sh       # Entrypoint API
│   ├── entrypoint-worker.sh    # Entrypoint Worker
│   └── docker-compose.yml      # Orchestration
│
├── tests/                      # Tests
│   ├── test_celery.py
│   └── test_concurrent.py
│
├── chat.html                   # Interface web
├── requirements.txt
└── README.md
```

---

## 🚀 Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
# Éditer avec vos clés
```

### 2. Docker Compose

```bash
cd docker

# Lancer API + Worker + Redis
docker-compose up -d

# Avec monitoring Flower
docker-compose --profile monitoring up -d

# Scaler les workers
docker-compose up -d --scale worker=5
```

### 3. Vérification

```bash
curl http://localhost:8007/health/full
# {"status":"ok","redis":"connected","celery_workers":"active","openai":"configured"}
```

---

## 📡 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/full` | Statut complet |
| `POST` | `/chat` | Chat sync (streaming direct) |
| `POST` | `/chat/async` | **Chat async (Celery)** ⚡ |
| `GET` | `/chat/{task_id}` | Status tâche |
| `GET` | `/stream/{session_id}` | SSE streaming |
| `POST` | `/embeddings` | Batch embeddings |
| `GET` | `/stats` | Stats queues |

### Exemple

```bash
# 1. Envoie requête async
curl -X POST http://localhost:8007/chat/async \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "priority": 5}'

# Réponse:
# {"status":"queued","task_id":"xxx","session_id":"yyy","stream_url":"/stream/yyy"}

# 2. Écoute le stream
curl -N http://localhost:8007/stream/yyy
```

---

## ⚙️ Variables d'environnement

```env
# OpenAI
OPENAI_API_KEY=sk-xxx

# Redis
REDIS_URL=redis://redis:6379/0

# API
PORT=8007
UVICORN_WORKERS=4

# Celery
CELERY_CONCURRENCY=4
CELERY_QUEUES=high,default,low
CELERY_LOGLEVEL=info

# Rate Limiting
LLM_RPM=500
LLM_TPM=100000
```

---

## 🐳 Docker

### Images

| Image | Description | Entrypoint |
|-------|-------------|------------|
| `Dockerfile.api` | FastAPI API | `entrypoint-api.sh` |
| `Dockerfile.worker` | Celery Worker | `entrypoint-worker.sh` |

### Services

| Service | Description | Scale |
|---------|-------------|-------|
| `api` | API FastAPI | 1 |
| `worker` | Celery workers | ∞ |
| `worker-high` | Workers priorité haute | ∞ |
| `redis` | Broker + cache | 1 |
| `flower` | Monitoring | 1 |

### Commandes

```bash
cd docker

# Démarrer
docker-compose up -d

# Logs
docker-compose logs -f api worker

# Scaler
docker-compose up -d --scale worker=10

# Monitoring (http://localhost:5555)
docker-compose --profile monitoring up -d

# Stop
docker-compose down
```

---

## 🧪 Tests

```bash
# Tests Celery
pytest tests/test_celery.py -v -s

# Tous les tests
pytest tests/ -v -s
```

---

## 🖥️ Interface Web

```bash
open chat.html
```

3 modes : **Celery**, **RabbitMQ**, **Direct**

---

## 📄 License

MIT
