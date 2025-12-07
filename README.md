# 🚀 LLM Stream API

> **API LLM scalable** avec Celery (Redis ou RabbitMQ).

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-green.svg)](https://docs.celeryq.dev)

---

## 🔄 Architecture

```
┌─────────────┐         ┌─────────────────┐
│   FastAPI   │ ──────► │     Celery      │
│    (API)    │         │    (Workers)    │
└─────────────┘         └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │     Broker      │
                        │  Redis ou AMQP  │
                        └─────────────────┘
```

**Un seul code Celery**, on choisit le broker via config :

| Broker | Variable | URL |
|--------|----------|-----|
| **Redis** (défaut) | `BROKER=redis` | `redis://localhost:6379/0` |
| **RabbitMQ** | `BROKER=rabbitmq` | `amqp://user:pass@host:5672/` |

---

## 📁 Structure

```
llm_fastapi_mq/
├── app/
│   ├── api/main.py         # FastAPI
│   ├── tasks/llm_tasks.py  # Tâches Celery
│   ├── celery_app.py       # Config Celery
│   └── config.py           # Variables
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── entrypoint-api.sh
│   ├── entrypoint-worker.sh
│   └── docker-compose.yml
├── tests/
├── chat.html
├── run.sh
└── requirements.txt
```

---

## ⚙️ Configuration

```env
# OpenAI
OPENAI_API_KEY=sk-xxx

# Broker (redis ou rabbitmq)
BROKER=redis
REDIS_URL=redis://localhost:6379/0

# Ou pour RabbitMQ (CloudAMQP, etc.)
# BROKER=rabbitmq
# RABBITMQ_URL=amqps://user:pass@host/vhost

# API
PORT=8007
UVICORN_WORKERS=4

# Celery
CELERY_CONCURRENCY=4
CELERY_QUEUES=high,default,low

# Rate Limiting
LLM_RPM=500
LLM_TPM=100000
```

---

## 🚀 Démarrage

```bash
# 1. Config
cp .env.example .env

# 2. Lancer (Redis par défaut)
./run.sh start

# Ou avec RabbitMQ
BROKER=rabbitmq RABBITMQ_URL=amqps://... ./run.sh start
```

---

## 📡 Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Chat sync (streaming direct) |
| `POST` | `/chat/async` | **Chat async (Celery)** ⚡ |
| `GET` | `/chat/{task_id}` | Status tâche |
| `GET` | `/stream/{session_id}` | SSE streaming |
| `POST` | `/embeddings` | Batch embeddings |

---

## 🐳 Commandes

```bash
./run.sh start         # Démarre API + Worker + Redis
./run.sh stop          # Arrête
./run.sh logs          # Logs
./run.sh scale 5       # 5 workers
./run.sh monitoring    # + Flower (port 5555)
./run.sh test          # Test endpoints
./run.sh status        # Status
./run.sh clean         # Nettoie tout
```

---

## 🧪 Tests

```bash
pytest tests/test_celery.py -v -s
```

---

## 📄 License

MIT
