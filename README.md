# 🚀 LLM Stream + RabbitMQ

> **Scalez votre API LLM de 50 à 1000+ requêtes simultanées** grâce au découplage via RabbitMQ.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)
[![Tests](https://img.shields.io/badge/tests-8%2F8%20passed-success.svg)](#-tests)

## 🎯 Le problème résolu

Votre API LLM lag quand plusieurs utilisateurs envoient des requêtes simultanément ? C'est normal : chaque appel OpenAI prend **10-60 secondes** et bloque un worker HTTP.

**Cette architecture résout le problème** en découplant le traitement :
- L'API retourne **immédiatement** (~100ms)
- Les workers LLM traitent les requêtes **en parallèle**
- Le client reçoit la réponse via **Server-Sent Events**

## 📊 Benchmarks réels

Tests exécutés avec 5 workers LLM :

| Métrique | Résultat |
|----------|----------|
| Temps de réponse API | **103ms** (fire & forget) |
| 5 requêtes parallèles | **50s** au lieu de 250s séquentiel |
| Gain de parallélisme | **5.0x** |
| Mode async vs sync | **13x** plus rapide pour libérer le serveur |
| Burst 10 requêtes | Absorbé en **613ms** |

```
┌──────────────────────────────────────────────────┐
│  RÉSULTATS DES TESTS                             │
├──────────────────────────────────────────────────┤
│  Temps total (5 req):   49.99s                   │
│  Si séquentiel:         249.07s                  │
│  Gain parallélisme:     5.0x ✅                  │
└──────────────────────────────────────────────────┘
```

## ✨ Fonctionnalités

- 🚀 **Streaming LLM** via OpenAI API (gpt-4o-mini)
- 📡 **RabbitMQ** pour le découplage producteur/consommateur
- 🔄 **SSE** (Server-Sent Events) pour le streaming temps réel
- 🐳 **Docker** avec auto-scaling des workers
- ⚙️ **Configuration via ENV** : ajustez workers selon la charge
- 🧪 **Tests pytest** : 8/8 tests validant le parallélisme

---

## 📐 Architecture

### Mode Synchrone (`/chat`) — Compatibilité

```
Client ──POST /chat──► FastAPI ──appel OpenAI──► Réponse (bloque 10-60s)
```

### Mode Asynchrone (`/chat/async`) — Production ⚡

```
┌─────────────┐    POST /chat/async   ┌─────────────────┐
│   Client    │ ────────────────────► │    FastAPI      │
│             │ ◄── session_id ────── │   (~100ms) ✅   │
└──────┬──────┘                       └────────┬────────┘
       │                                       │
       │                                       ▼
       │ SSE                          ┌─────────────────┐
       │                              │    RabbitMQ     │
       │                              │   (llm_tasks)   │
       │                              └────────┬────────┘
       │                                       │
       │                              ┌────────┴────────┐
       │                              ▼        ▼        ▼
       │                           Worker   Worker   Worker
       │                           LLM #1   LLM #2   LLM #N
       │                              │        │        │
       │ GET /stream/{id}             └────────┴────────┘
       │                                       │
       └───────────────────────────────────────┘
                                         chunks SSE
```

### Comparaison des modes

| Aspect | `/chat` (sync) | `/chat/async` |
|--------|----------------|---------------|
| Latence HTTP | 10-60s (bloqué) | **~100ms** |
| Workers HTTP | 1 occupé par requête | Libéré instantanément |
| Scalabilité | Limitée | **Horizontale** |
| Use case | Dev/tests | **Production** |

---

## ⚙️ Variables d'environnement

| Variable | Description | Défaut | Requis |
|----------|-------------|--------|--------|
| `OPENAI_API_KEY` | Clé API OpenAI | - | ✅ |
| `RABBIT_MQ` | URL RabbitMQ (CloudAMQP ou local) | - | ✅ |
| `UVICORN_WORKERS` | Workers HTTP (routing) | `4` | ❌ |
| `LLM_WORKERS` | Workers LLM (traitement OpenAI) | `3` | ❌ |
| `PORT` | Port de l'API | `8007` | ❌ |

### Exemple `.env`

```env
# === REQUIS ===
OPENAI_API_KEY=sk-proj-xxxxx
RABBIT_MQ=amqps://user:pass@coral.rmq.cloudamqp.com/vhost

# === SCALING (optionnel) ===
UVICORN_WORKERS=4   # Workers HTTP
LLM_WORKERS=5       # Workers LLM (1 worker = 1 requête OpenAI en parallèle)
PORT=8007
```

---

## 🚀 Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
# Éditer avec vos clés OpenAI et RabbitMQ
```

### 2. Build & Run

```bash
# Option 1 : Script
./run.sh start

# Option 2 : Docker manuel
docker build -t llm-fastapi-mq .
docker run -d --name llm-mq-poc \
  -p 8007:8007 \
  -e LLM_WORKERS=5 \
  --env-file .env \
  llm-fastapi-mq
```

### 3. Vérification

```bash
# Health check
curl http://localhost:8007/health/full
# ✅ {"status":"ok","rabbitmq":"connected","openai":"configured"}

# Logs de démarrage
docker logs llm-mq-poc
# ========================================
#   LLM FastAPI + RabbitMQ
# ========================================
#   Uvicorn workers: 4
#   LLM workers:     5
# ========================================
```

---

## 📡 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check basique |
| `GET` | `/health/full` | Statut RabbitMQ + OpenAI |
| `GET` | `/stats` | Tâches en attente |
| `POST` | `/chat` | Mode sync (legacy) |
| `POST` | `/chat/async` | **Mode async (recommandé)** ⚡ |
| `GET` | `/stream/{session_id}` | Stream SSE des chunks |

### Exemple : Mode Async (recommandé)

```bash
# 1. Envoie la requête → retour immédiat (~100ms)
curl -X POST http://localhost:8007/chat/async \
  -H "Content-Type: application/json" \
  -d '{"message": "Explique Docker en 3 points"}'

# Réponse instantanée :
# {"status":"queued","session_id":"abc-123","stream_url":"/stream/abc-123"}

# 2. Écoute le stream SSE
curl -N http://localhost:8007/stream/abc-123
# data: {"chunk": "Docker"}
# data: {"chunk": " est"}
# data: {"chunk": " un"}
# ...
# data: {"type": "done"}
```

---

## 🧪 Tests

8 tests pytest validant le parallélisme :

```bash
# Dans le conteneur Docker
docker exec llm-mq-poc pytest tests/ -v -s

# Ou localement
pip install pytest pytest-asyncio httpx
pytest tests/ -v -s
```

### Résultats des tests

```
tests/test_concurrent.py::TestHealthCheck::test_health ✅
tests/test_concurrent.py::TestHealthCheck::test_health_full ✅
tests/test_concurrent.py::TestAsyncMode::test_chat_async_returns_immediately ✅ (103ms)
tests/test_concurrent.py::TestAsyncMode::test_stream_receives_chunks ✅
tests/test_concurrent.py::TestParallelProcessing::test_parallel_5_requests ✅ (5.0x gain)
tests/test_concurrent.py::TestParallelProcessing::test_compare_sync_vs_async ✅ (13x)
tests/test_concurrent.py::TestLoadCapacity::test_queue_stats ✅
tests/test_concurrent.py::TestLoadCapacity::test_burst_10_requests ✅ (613ms)

========================= 8 passed in 92.44s =========================
```

---

## 📊 Scaling

### Formule du nombre de workers LLM

```
LLM_WORKERS = (requêtes/minute) × (temps moyen génération en minutes)

Exemple :
- 60 requêtes/minute attendues
- 30 secondes par génération (0.5 min)
- Workers = 60 × 0.5 = 30 workers
```

### Configurations recommandées

| Charge | LLM_WORKERS | UVICORN_WORKERS | RAM |
|--------|-------------|-----------------|-----|
| Dev | 2 | 1 | 512 MB |
| Petit (10 users) | 5 | 2 | 1 GB |
| Moyen (50 users) | 15 | 4 | 2 GB |
| Production (100+ users) | 30-50 | 4 | 4-8 GB |

### Lancer avec plus de workers

```bash
docker run -d --name llm-prod \
  -p 8007:8007 \
  -e LLM_WORKERS=30 \
  -e UVICORN_WORKERS=4 \
  --env-file .env \
  llm-fastapi-mq
```

---

## 🖥️ Interface Web

```bash
# Windows
start chat.html

# macOS / Linux
open chat.html
# ou
python -m http.server 3000 && open http://localhost:3000/chat.html
```

**Fonctionnalités :**
- 💬 Chat temps réel avec streaming
- 🔄 Switch mode RabbitMQ / Direct
- 📊 Indicateurs de statut (API, Queue, Stream)
- 📱 Design responsive

---

## 📁 Structure du projet

```
llm_fastapi_mq/
├── main.py                 # API FastAPI
├── config.py               # Variables d'environnement
├── Dockerfile              # Image multi-workers
├── entrypoint.sh           # Lance API + Workers auto
├── chat.html               # Interface web
├── services/
│   ├── connection_pool.py  # Pool connexions RabbitMQ
│   ├── llm_worker.py       # Worker LLM (scalable)
│   ├── rabbit_publisher.py # Publisher
│   └── rabbit_consumer.py  # Consumer SSE
└── tests/
    ├── conftest.py         # Config pytest
    └── test_concurrent.py  # Tests parallélisme
```

---

## 🐛 Troubleshooting

### Requêtes traitées séquentiellement

```bash
# Vérifier les workers actifs
docker top llm-mq-poc | grep llm_worker

# Augmenter si nécessaire
docker run -e LLM_WORKERS=10 ...
```

### Erreur connexion RabbitMQ

```bash
# Plan CloudAMQP gratuit = 20 connexions max
# Réduire les workers
docker run -e LLM_WORKERS=3 -e UVICORN_WORKERS=2 ...
```

### Erreur OpenAI (caractères Windows)

```bash
# Nettoyer les \r du .env
sed -i 's/\r$//' .env
```

### Monitoring

```bash
# Tâches en attente
curl http://localhost:8007/stats
# {"pending_tasks":5,"queue":"llm_tasks","status":"ok"}

# Health complet
curl http://localhost:8007/health/full
```

---

## 📄 License

MIT

---

## 🤝 Contribution

1. Fork le projet
2. Créer une branche (`git checkout -b feature/amazing`)
3. Commit (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing`)
5. Ouvrir une Pull Request

---

<p align="center">
  <b>⭐ Si ce projet vous aide, laissez une étoile !</b>
</p>
