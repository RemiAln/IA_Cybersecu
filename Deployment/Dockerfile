# Image de l'API Digital Social Score (étape 3)
#
# À construire DEPUIS LA RACINE du projet (le contexte doit contenir
# data_transformation/ et modeles/) :
#   docker build -f Deployment/Dockerfile -t digital-social-score .

FROM python:3.12-slim

WORKDIR /app

# PyTorch version CPU (~200 Mo au lieu de plus de 2 Go pour la version GPU),
# même version que celle utilisée pour l'entraînement
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Même arborescence que le projet : l'API s'importe comme Deployment.api
# Code de l'API, fonction de nettoyage et modèle entraîné uniquement :
# aucune donnée du dataset n'est copiée.
COPY Deployment/api.py ./Deployment/api.py
COPY data_transformation/nettoyage.py ./data_transformation/nettoyage.py
COPY modeles/bert ./modeles/bert

# Cloud Run indique le port à utiliser dans la variable PORT (8080 par défaut)
ENV PORT=8080
CMD exec uvicorn Deployment.api:app --host 0.0.0.0 --port ${PORT}
