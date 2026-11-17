# Image de l'API Digital Social Score (étape 3)
#
# À construire DEPUIS LA RACINE du projet (le contexte doit contenir
# data_transformation/ et modeles/) :
#   docker build -f Deployment/Dockerfile -t digital-social-score .

FROM python:3.12-slim

WORKDIR /app

# PyTorch version CPU (~200 Mo au lieu de plus de 2 Go pour la version GPU),
# même version que celle utilisée pour l'entraînement.
# Installé AVANT laya, sinon pip installerait la version GPU.
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
# Sécurité (TP2, étape 5) : pip et setuptools (installé avec torch) à jour,
# sinon ils contiennent des failles connues (path traversal) signalées par
# pip-audit et Trivy.
RUN pip install --no-cache-dir --upgrade pip setuptools

# Même arborescence que le projet : l'API s'importe comme Deployment.api
# Code de l'API, fonction de nettoyage et modèle entraîné uniquement :
# aucune donnée du dataset n'est copiée.
COPY Deployment/api.py ./Deployment/api.py
# Défenses du TP2 (étape 3) : normalisation anti-évasion, limite de débit et
# réponse appauvrie anti-extraction
COPY Deployment/normalisation.py ./Deployment/normalisation.py
COPY Deployment/defenses_api.py ./Deployment/defenses_api.py
COPY data_transformation/nettoyage.py ./data_transformation/nettoyage.py
# Modèle Laya (~650 Mo). Le sous-dossier checkpoint_latest/ (copie de sauvegarde
# de l'entraînement, inutile pour prédire) est exclu par .dockerignore / .gcloudignore.
COPY modeles/laya ./modeles/laya

# Sécurité (TP2, étape 5) : l'API ne tourne PAS en root. Utilisateur sans shell
# ni dossier personnel ; UID numérique pour que Kubernetes puisse vérifier
# runAsNonRoot. Les fichiers copiés restent en lecture seule pour lui.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin dss
# Seul /tmp est accessible en écriture (volume monté par Kubernetes, le reste
# du système de fichiers est en lecture seule) : caches de Hugging Face / torch.
ENV HOME=/tmp HF_HOME=/tmp/hf PYTHONDONTWRITEBYTECODE=1
USER 10001

# Port d'écoute de l'API dans le conteneur (8080)
ENV PORT=8080
CMD exec uvicorn Deployment.api:app --host 0.0.0.0 --port ${PORT}
