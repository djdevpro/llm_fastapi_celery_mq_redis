# LLM Stream + RabbitMQ

POC de streaming LLM avec découplage via RabbitMQ. Permet de décharger le streaming des réponses LLM du serveur principal vers des workers indépendants.

## Architecture

### Mode Synchrone (`/chat`) - Compatibilité
```
┌─────────────┐     POST /chat      ┌─────────────────┐
│   Client    │ ──────────────────► │    FastAPI      │
│  (Browser)  │ ◄────stream──────── │    (traite)     │
└─────────────┘                     └─────────────────┘
```

### Mode Asynchrone (`/chat/async`) - Haute charge ⚡
```
┌─────────────┐    POST /chat/async   ┌─────────────────┐
│   Client    │ ────────────────────► │    FastAPI      │
│  (Browser)  │ ◄──{session_id}────── │  (fire & forget)│
└──────┬──────┘                       └────────┬────────┘
       │                                       │
       │                                       │ Publie tâche
       │ SSE                                   ▼
       │                              ┌─────────────────┐
       │                              │    RabbitMQ     │
       │                              │   (llm_tasks)   │
       │                              └────────┬────────┘
       │                                       │
       │                                       │ Consomme
       │                                       ▼
       │                              ┌─────────────────┐
       │                              │  LLM Worker(s)  │ x N instances
       │                              │  (llm_worker.py)│
       │                              └────────┬────────┘
       │                                       │
       │ GET /stream/{session_id}              │ Publie chunks
       │                                       ▼
       └────────────────────────────► ┌─────────────────┐
                                      │ llm_session_{id}│
                                      └─────────────────┘
```

### Avantages du mode asynchrone

| Aspect | Sync (`/chat`) | Async (`/chat/async`) |
|--------|----------------|----------------------|
| Latence HTTP | Bloqué pendant génération | ~50ms retour immédiat |
| Workers HTTP | 1 par requête active | Libéré instantanément |
| Scalabilité | Limitée par uvicorn | Workers indépendants |
| Charge | ~100 req/s | ~1000+ req/s |

## Fonctionnalités

- 🚀 **Streaming LLM** via OpenAI API (gpt-4o-mini)
- 📡 **RabbitMQ** pour le découplage producteur/consommateur
- 🔄 **SSE** (Server-Sent Events) pour le streaming client
- 🐳 **Docker** ready
- ⚡ **Deux modes** : RabbitMQ (async) ou Direct (sync)

## Prérequis

- Docker
- Compte OpenAI (API Key)
- Compte CloudAMQP ou RabbitMQ local

## Installation

### 1. Configuration

```bash
cp .env.example .env
```

Éditer `.env` :

```env
OPENAI_API_KEY=sk-your-openai-api-key
RABBIT_MQ=amqps://user:password@host/vhost
```

### 2. Build & Run

```bash
# Build et lancer
./run.sh start

# Ou manuellement
docker build -t llm-fastapi-mq .
docker run -d --name llm-mq-poc -p 8007:8007 --env-file .env llm-fastapi-mq
```

### 3. Test

```bash
# Health check
curl http://localhost:8007/health

# Test OpenAI
curl http://localhost:8007/test

# Chat avec streaming
curl -N -X POST http://localhost:8007/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour !"}'
```

## API Endpoints

| Méthode | Endpoint | Description | Mode |
|---------|----------|-------------|------|
| `GET` | `/health` | Health check basique | - |
| `GET` | `/health/full` | Health check + statut RabbitMQ | - |
| `GET` | `/test` | Test connexion OpenAI | - |
| `GET` | `/stats` | Tâches en attente dans la queue | - |
| `POST` | `/chat` | Streaming synchrone (legacy) | Sync |
| `POST` | `/chat/async` | Fire-and-forget, retourne session_id | **Async** ⚡ |
| `GET` | `/stream/{session_id}` | SSE - consomme les chunks | Async |

### POST /chat

**Request:**
```json
{
  "message": "Explique-moi les microservices",
  "session_id": "optional-custom-id"
}
```

**Response:** Stream text/plain + Header `X-Session-ID`

### GET /stream/{session_id}

**Response:** SSE avec events :
```
data: {"chunk": "Bonjour"}

data: {"chunk": " !"}

data: {"type": "done"}
```

## Interface Web

### Lancer l'interface

```bash
# Option 1 : Ouvrir directement le fichier
# Windows
start chat.html

# macOS
open chat.html

# Linux
xdg-open chat.html

# Option 2 : Serveur local (évite les problèmes CORS)
python -m http.server 3000
# Puis ouvrir http://localhost:3000/chat.html

# Option 3 : Extension VS Code "Live Server"
# Clic droit sur chat.html → "Open with Live Server"
```

### Configuration

Par défaut, l'interface se connecte à `http://localhost:8007`. Pour changer l'URL de l'API, modifier la variable dans `chat.html` :

```javascript
const API_URL = 'http://localhost:8007';
```

### Modes disponibles

| Mode | Description | Flux |
|------|-------------|------|
| **RabbitMQ** | Découplé via message queue | `POST /chat` → RabbitMQ → `SSE /stream/{id}` |
| **Direct** | Stream HTTP classique | `POST /chat` → Stream response |

### Fonctionnalités

- 💬 Chat en temps réel avec streaming
- 🔄 Switch entre mode RabbitMQ et Direct
- ⏱️ Timestamps sur les messages
- 🎯 Indicateur de typing pendant la génération
- 📊 Status indicators (API, Queue, Stream)
- 📱 Responsive design

## Structure du projet

```
llm_fastapi_mq/
├── main.py                 # Application FastAPI (routeur)
├── config.py               # Configuration (env vars)
├── requirements.txt        # Dépendances Python
├── Dockerfile              # Image Docker
├── entrypoint.sh           # Script d'entrée Docker
├── run.sh                  # Script de gestion
├── chat.html               # Interface web
├── .env                    # Variables d'environnement
├── .env.example            # Template env
└── services/
    ├── __init__.py         # Module init
    ├── connection_pool.py  # Pool de connexions RabbitMQ (singleton)
    ├── llm_worker.py       # Worker LLM indépendant (scalable)
    ├── rabbit_publisher.py # Publisher RabbitMQ (legacy)
    └── rabbit_consumer.py  # Consumer RabbitMQ
```

## Scripts

```bash
./run.sh start    # Build + Run
./run.sh stop     # Stop container
./run.sh restart  # Restart
./run.sh logs     # Voir les logs
./run.sh shell    # Shell dans le container
./run.sh test     # Test les endpoints
```

## Scaling (Haute charge) ⚡

### Étape 1 : Lancer le serveur FastAPI

```bash
# Un seul serveur HTTP suffit (il ne fait que router)
./run.sh start
```

### Étape 2 : Lancer les workers LLM

```bash
# Localement - Plusieurs workers en parallèle
python -m services.llm_worker &
python -m services.llm_worker &
python -m services.llm_worker &

# Ou avec Docker
docker run -d --name worker-1 --env-file .env llm-fastapi-mq python -m services.llm_worker
docker run -d --name worker-2 --env-file .env llm-fastapi-mq python -m services.llm_worker
docker run -d --name worker-3 --env-file .env llm-fastapi-mq python -m services.llm_worker
```

### Étape 3 : Utiliser le mode async

```bash
# POST sur /chat/async au lieu de /chat
curl -X POST http://localhost:8007/chat/async \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour !"}'

# Réponse immédiate :
# {"status": "queued", "session_id": "abc-123", "stream_url": "/stream/abc-123"}

# Puis écouter le stream SSE :
curl -N http://localhost:8007/stream/abc-123
```

### Monitoring

```bash
# Voir les tâches en attente
curl http://localhost:8007/stats

# Health check complet
curl http://localhost:8007/health/full
```

### Kubernetes (production)

```yaml
# api-deployment.yaml - Serveur HTTP léger
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-api
spec:
  replicas: 2  # 2 suffisent (stateless, rapide)
  template:
    spec:
      containers:
      - name: api
        resources:
          limits:
            memory: "256Mi"
            cpu: "200m"
---
# worker-deployment.yaml - Workers LLM (le vrai travail)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-worker
spec:
  replicas: 10  # Scaler selon la charge
  template:
    spec:
      containers:
      - name: worker
        command: ["python", "-m", "services.llm_worker"]
        resources:
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Calcul du nombre de workers

```
Formule : workers = (requêtes/minute) × (temps moyen génération en minutes)

Exemple :
- 100 requêtes/minute
- 30 secondes par génération (0.5 min)
- Workers nécessaires = 100 × 0.5 = 50 workers
```

## Troubleshooting

### Connection error

Si vous avez une erreur de connexion OpenAI, vérifiez que votre `.env` n'a pas de caractères `\r` (Windows). Le `config.py` utilise `.strip()` pour nettoyer les variables.

### RabbitMQ timeout

Augmentez le timeout dans `rabbit_consumer.py` si les réponses LLM sont longues.

## License

MIT
