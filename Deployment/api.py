"""
TP1 - Étape 3 : API "Digital Social Score"

Reçoit un texte et renvoie un score de toxicité de 0 à 100, calculé par le
modèle Laya entraîné à l'étape 2 (dossier modeles/laya).

Lancement local : uvicorn Deployment.api:app      (depuis la racine du projet)
Documentation   : http://127.0.0.1:8000/docs  (page générée automatiquement)
"""

import json
import os

# Avant d'importer laya : pas de TensorFlow (blocage connu), et aucun accès à
# Internet pour le modèle (il est déjà dans l'image, rien à télécharger).
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import laya
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, Field

from data_transformation.nettoyage import nettoyer

DOSSIER_MODELE = "modeles/laya"   # relatif à la racine du projet (ou /app dans le conteneur)
LONGUEUR_MAX = 128                # identique à l'entraînement (modele_laya.py)
SEUIL_TOXIQUE = 0.5               # identique à l'évaluation : P(note >= 1) >= 0.5
NB_NOTES = 6                      # notes 0 à 5

# ---------------------------------------------------------------------------
# Chargement du modèle : UNE SEULE FOIS, au démarrage de l'API
# (~650 Mo : le recharger à chaque requête prendrait trop de temps)
# ---------------------------------------------------------------------------
agent = laya.load(DOSSIER_MODELE, device="cpu")

# La question posée au modèle est relue dans le modèle lui-même (questions.json) :
# on est certain de poser EXACTEMENT la question apprise à l'entraînement.
with open(os.path.join(DOSSIER_MODELE, "questions.json"), encoding="utf-8") as f:
    QUESTIONS = json.load(f)
ID_QUESTION = next(iter(QUESTIONS))          # "toxicite"


def predire(texte: str) -> np.ndarray:
    """Probabilités des 6 notes (0 à 5) pour un texte déjà nettoyé."""
    reponse = agent.predict_batch([texte], QUESTIONS, max_len=LONGUEUR_MAX)[0]
    probas = reponse["answers"][ID_QUESTION]["probabilities"]
    return np.array([probas[str(k)] for k in range(NB_NOTES)])


# Échauffement : le premier calcul est toujours plus lent ; on le fait ici,
# avant que l'API n'accepte des requêtes.
predire("gg")

app = FastAPI(
    title="Digital Social Score",
    description="Détection de toxicité : renvoie un score de 0 (sain) à 100 (très toxique).",
    version="1.0",
)


# ---------------------------------------------------------------------------
# Format des requêtes et des réponses (validé automatiquement par FastAPI)
# ---------------------------------------------------------------------------
class Requete(BaseModel):
    # Validation d'entrée : texte obligatoire, entre 1 et 1 000 caractères
    texte: str = Field(..., min_length=1, max_length=1000, examples=["gg wp team"])


class Reponse(BaseModel):
    score: float           # 0 à 100
    note: int              # note la plus probable, de 0 à 5
    toxique: bool          # True si P(note >= 1) >= 0.5


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Vérifie que l'API répond (utilisé par Kubernetes et les tests de charge)."""
    return {"statut": "ok"}


@app.post("/score", response_model=Reponse)
def score(requete: Requete):
    # 1. Même nettoyage qu'à l'entraînement (minuscules, ponctuation...)
    texte = nettoyer(requete.texte)

    # 2. Prédiction : probabilités des 6 notes (0 à 5)
    probas = predire(texte)

    # 3. Score 0-100 = note moyenne attendue x 20 (même calcul qu'à l'étape 2)
    score_0_100 = float(probas @ np.arange(NB_NOTES) * 20)

    return Reponse(
        score=round(score_0_100, 1),
        note=int(probas.argmax()),
        toxique=bool(1 - probas[0] >= SEUIL_TOXIQUE),
    )
