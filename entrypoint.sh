#!/bin/bash

# Charge les variables depuis .env si le fichier existe
if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | xargs)
fi

# Exécute la commande passée
exec "$@"
