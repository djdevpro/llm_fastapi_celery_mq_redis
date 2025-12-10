# 🚀 LLM Stream API

> **Proxy OpenAI scalable** avec Celery + Redis pour gérer la charge des appels LLM.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-green.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)
[![OpenAI Compatible](https://img.shields.io/badge/OpenAI-compatible-orange.svg)](https://platform.openai.com)

---

## 🎯 Problème résolu

Les appels LLM (OpenAI) prennent **10-60 secondes** et bloquent vos workers HTTP.

**Ce proxy** :
- ⚡ File d'attente intelligente (Celery)
- 🔄 Rate limiting centralisé
- 📡 Streaming SSE temps réel
- 🔌 **Compatible SDK OpenAI** (drop-in replacement)

---

## 📐 Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  SDK OpenAI     │────▶│   PROXY API    │────▶│   Celery/Redis  │
│  (any language) │     │  /v1/chat/...   │     │   (queue)       │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                  ┌──────▼──────┐
                                                  │   OpenAI    │
                                                  └─────────────┘
```

---

## 🔌 Usage (SDK OpenAI)

### Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8007/v1",  # Proxy
    api_key="not-needed"
)

# Streaming
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")

# Non-streaming
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=False
)
print(response.choices[0].message.content)
```

### Node.js

```javascript
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'http://localhost:8007/v1',
  apiKey: 'not-needed'
});

const stream = await client.chat.completions.create({
  model: 'gpt-4o-mini',
  messages: [{ role: 'user', content: 'Hello!' }],
  stream: true
});

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content || '');
}
```

### cURL

```bash
curl http://localhost:8007/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## 📁 Structure

```
llm_fastapi_mq/
├── app/
│   ├── api/
│   │   ├── main.py           # FastAPI
│   │   └── proxy.py          # Proxy OpenAI compatible
│   ├── tasks/llm_tasks.py    # Tâches Celery
│   ├── celery_app.py
│   └── config.py
│
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   └── docker-compose.yml
│
├── ui/                       # Interface chat
│   ├── chat.html
│   └── Dockerfile
│
├── examples/
│   ├── client_openai.py      # Exemple Python
│   └── client_openai.js      # Exemple Node.js
│
├── tests/
├── run.sh
└── requirements.txt
```

---

## ⚙️ Configuration `.env`

```env
# === REQUIS ===
OPENAI_API_KEY=sk-proj-xxxxx

# === REDIS ===
REDIS_URL=redis://redis:6379/0

# === API ===
PORT=8007
UVICORN_WORKERS=4

# === CELERY ===
CELERY_CONCURRENCY=4
CELERY_QUEUES=high,default,low
CELERY_LOGLEVEL=info

# === UI ===
UI_PORT=3000
API_URL=http://localhost:8007

# === MONITORING ===
FLOWER_PORT=5555

# === RATE LIMITING (Celery natif) ===
CELERY_RATE_LIMIT=100/m
```

---

## 🚀 Démarrage

```bash
# 1. Config
cp .env.example .env

# 2. Lancer
./run.sh start

# 3. Tester
python examples/client_openai.py

# 4. Ouvrir
#    UI:   http://localhost:3000
#    API:  http://localhost:8007/docs
```

---

## 📡 Endpoints

### Proxy OpenAI (`/v1`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/v1/chat/completions` | Chat (streaming & non-streaming) |
| `GET` | `/v1/models` | Liste des modèles |

### API interne

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Chat async (Celery) |
| `GET` | `/stream/{session_id}` | Stream SSE |
| `POST` | `/embeddings` | Batch embeddings |
| `GET` | `/stats` | Stats queues |

---

## 🐳 Services Docker

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8007 | FastAPI + Proxy OpenAI |
| `worker` | - | Celery workers |
| `redis` | - | Broker (interne) |
| `ui` | 3000 | Interface chat |
| `flower` | 5555 | Monitoring (optionnel) |

---

## 🛠️ Commandes

```bash
./run.sh start         # Démarre tout
./run.sh stop          # Arrête
./run.sh restart       # Redémarre
./run.sh logs          # Tous les logs
./run.sh logs api      # Logs API
./run.sh logs worker   # Logs Worker
./run.sh status        # Status
./run.sh scale 5       # 5 workers
./run.sh monitoring    # + Flower
./run.sh test          # Tests
./run.sh build         # Build
./run.sh clean         # Nettoie
```

---

## 📊 Scaling

```
Workers = (Requêtes/min) × (Temps moyen/min) / Concurrency

Exemple: 100 req/min × 0.5 min / 4 = 13 workers
```

| Charge | Workers | Concurrency |
|--------|---------|-------------|
| Dev | 1 | 2 |
| 50 req/min | 4 | 4 |
| 200 req/min | 10 | 4 |
| 500 req/min | 25 | 4 |

---

## 🔧 Features

- ✅ **Proxy OpenAI compatible** (SDK standard)
- ✅ File d'attente Celery
- ✅ Rate limiting (token bucket Redis)
- ✅ Retry automatique (backoff exponentiel)
- ✅ 3 queues prioritaires (high/default/low)
- ✅ Streaming SSE
- ✅ Monitoring Flower
- ✅ Multi-langage (Python, Node, Go, etc.)

---

## 📄 License

MIT
