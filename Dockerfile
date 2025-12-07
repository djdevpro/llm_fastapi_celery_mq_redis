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

EXPOSE 8007

ENTRYPOINT ["/entrypoint.sh"]
# Force asyncio loop au lieu de uvloop
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007", "--loop", "asyncio"]
