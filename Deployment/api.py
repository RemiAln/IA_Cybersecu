"""
TP1 - Étape 3 : API "Digital Social Score"

Reçoit un texte et renvoie un score de toxicité de 0 à 100, calculé par le
modèle BERT-Mini entraîné à l'étape 2 (dossier modeles/bert).

Lancement local : uvicorn Deployment.api:app --reload     (depuis la racine du projet)
Documentation   : http://127.0.0.1:8000/docs  (page générée automatiquement)
"""

import numpy as np
import torch
from fastapi import FastAPI
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from data_transformation.nettoyage import nettoyer

DOSSIER_MODELE = "modeles/bert"   # relatif à la racine du projet (ou /app dans le conteneur)
LONGUEUR_MAX = 32          # identique à l'entraînement (modele_bert.py)
SEUIL_TOXIQUE = 0.5        # identique à l'évaluation : P(note >= 1) >= 0.5

# ---------------------------------------------------------------------------
# Chargement du modèle : UNE SEULE FOIS, au démarrage de l'API
# (le recharger à chaque requête prendrait plusieurs secondes)
# ---------------------------------------------------------------------------
tokenizer = AutoTokenizer.from_pretrained(DOSSIER_MODELE)
modele = AutoModelForSequenceClassification.from_pretrained(DOSSIER_MODELE)
modele.eval()

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
    """Vérifie que l'API répond (utilisé par le cloud et les tests de charge)."""
    return {"statut": "ok"}


@app.post("/score", response_model=Reponse)
def score(requete: Requete):
    # 1. Même nettoyage qu'à l'entraînement (minuscules, ponctuation...)
    texte = nettoyer(requete.texte)

    # 2. Prédiction : probabilités des 6 notes (0 à 5)
    entree = tokenizer([texte], truncation=True, max_length=LONGUEUR_MAX,
                       return_tensors="pt")
    with torch.no_grad():
        probas = torch.softmax(modele(**entree).logits, dim=1)[0].numpy()

    # 3. Score 0-100 = note moyenne attendue x 20 (même calcul qu'à l'étape 2)
    score_0_100 = float(probas @ np.arange(len(probas)) * 20)

    return Reponse(
        score=round(score_0_100, 1),
        note=int(probas.argmax()),
        toxique=bool(1 - probas[0] >= SEUIL_TOXIQUE),
    )
