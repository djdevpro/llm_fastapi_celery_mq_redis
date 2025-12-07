# LLM Stream + RabbitMQ

POC de streaming LLM avec découplage via RabbitMQ. Permet de décharger le streaming des réponses LLM du serveur principal vers des workers indépendants.

## Architecture

```
┌─────────────┐     POST /chat      ┌─────────────────┐
│   Client    │ ──────────────────► │    FastAPI      │
│  (Browser)  │                     │    Service      │
└─────────────┘                     └────────┬────────┘
       ▲                                     │
       │                                     │ Publish chunks
       │ SSE                                 ▼
       │                            ┌─────────────────┐
       │                            │    RabbitMQ     │
       │                            │  (CloudAMQP)    │
       │                            └────────┬────────┘
       │                                     │
       │ GET /stream/{session_id}            │ Consume
       │                                     ▼
       └──────────────────────────── ┌─────────────────┐
                                     │   SSE Stream    │
                                     └─────────────────┘
```

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

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/test` | Test connexion OpenAI |
| `POST` | `/chat` | Envoie un message, retourne un stream + publie dans RabbitMQ |
| `GET` | `/stream/{session_id}` | SSE - consomme les chunks depuis RabbitMQ |

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
├── main.py                 # Application FastAPI
├── config.py               # Configuration (env vars)
├── requirements.txt        # Dépendances Python
├── Dockerfile              # Image Docker
├── entrypoint.sh           # Script d'entrée Docker
├── run.sh                  # Script de gestion
├── chat.html               # Interface web
├── .env                    # Variables d'environnement
├── .env.example            # Template env
└── services/
    ├── rabbit_publisher.py # Publisher RabbitMQ
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

## Scaling

Pour scaler les workers qui consomment les messages :

```bash
# Lancer plusieurs consumers
docker run -d --name worker-1 --env-file .env llm-fastapi-mq
docker run -d --name worker-2 --env-file .env llm-fastapi-mq
```

Avec Kubernetes :
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-stream-worker
spec:
  replicas: 3
  # ...
```

## Troubleshooting

### Connection error

Si vous avez une erreur de connexion OpenAI, vérifiez que votre `.env` n'a pas de caractères `\r` (Windows). Le `config.py` utilise `.strip()` pour nettoyer les variables.

### RabbitMQ timeout

Augmentez le timeout dans `rabbit_consumer.py` si les réponses LLM sont longues.

## License

MIT
