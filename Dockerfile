FROM python:3.12-slim

WORKDIR /app

# Certificats SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ============================================================
# Configuration via variables d'environnement
# ============================================================
# Workers HTTP (uvicorn) - gère les requêtes entrantes
ENV UVICORN_WORKERS=4

# Workers LLM - traite les tâches OpenAI depuis RabbitMQ
ENV LLM_WORKERS=3

# Port de l'API
ENV PORT=8007

EXPOSE ${PORT}

ENTRYPOINT ["/entrypoint.sh"]
