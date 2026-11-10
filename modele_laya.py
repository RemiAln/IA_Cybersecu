"""
TP1 - Étape 2 : modèle de décision (Laya)

Pré-requis : pip install laya
Usage      : python modele_laya.py
Sortie     : modeles/laya/          (modèle entraîné)
             resultats/laya.json    (précision, rappel, F1, temps)
"""

import json
import os
from pathlib import Path

os.environ.setdefault("USE_TF", "0")   # évite un blocage connu au chargement (doc Laya)

import numpy as np

import laya
from laya.train import TrainConfig, finetune, resolve_checkpoint_dir

from evaluation import NB_NOTES, Chrono, charger_donnees, evaluer

# ---------------------------------------------------------------------------
# PARAMÈTRES À MODIFIER
# ---------------------------------------------------------------------------
CHECKPOINT = "multilingual"   # le plus léger des modèles Laya (322 M de paramètres)
LONGUEUR_MAX = 128            # longueur max d'un texte, en tokens
NB_EXEMPLES_TRAIN = 2000      # nb de messages utilisés pour l'entraînement
NB_EXEMPLES_VALID = 500       # nb de messages de validation pendant l'entraînement
EPOCHS = 1                    # nb de passages sur les données d'entraînement
# ---------------------------------------------------------------------------

# Question posée à Laya pour chaque message : une note de 0 à 5
QUESTIONS = {
    "toxicite": {
        "type": "score",
        "instructions": "How toxic is this video game chat message "
                        "(insults, racism, harassment, hate speech)?",
        # niveaux ordonnés du plus faible au plus fort, un par note 0..5
        "criteria": ["not toxic", "slightly toxic", "moderately toxic",
                     "toxic", "very toxic", "extremely toxic"],
    }
}


def predire(agent, textes) -> np.ndarray:
    """Probabilités des 6 notes, lues dans la réponse de Laya."""
    reponses = agent.predict_batch(textes, QUESTIONS, batch_size=64, max_len=LONGUEUR_MAX)
    return np.array([[r["answers"]["toxicite"]["probabilities"][str(k)] for k in range(NB_NOTES)]
                     for r in reponses])


def preparer_jsonl(df, chemin):
    """Format attendu par laya.train : une ligne {state, questions, expected} par message."""
    with open(chemin, "w", encoding="utf-8") as f:
        for texte, note in zip(df["message"], df["label"]):
            f.write(json.dumps({"state": texte, "questions": QUESTIONS,
                                "expected": {"toxicite": int(note)}}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    train, valid, test = charger_donnees()

    # 1. Sous-ensembles tirés au hasard, en gardant la répartition des notes
    echantillon = train.groupby("label", group_keys=False).apply(
        lambda g: g.sample(frac=min(1, NB_EXEMPLES_TRAIN / len(train)), random_state=42))
    Path("modeles").mkdir(exist_ok=True)
    preparer_jsonl(echantillon, "modeles/laya_train.jsonl")
    preparer_jsonl(valid.sample(min(NB_EXEMPLES_VALID, len(valid)), random_state=42),
                   "modeles/laya_valid.jsonl")

    # 2. Entraînement (fine-tuning) de Laya sur nos données
    resume = finetune(
        data="modeles/laya_train.jsonl",
        model_dir=resolve_checkpoint_dir(CHECKPOINT),
        output_dir="modeles/laya",
        config=TrainConfig(epochs=EPOCHS, loss="soft-ce", max_len=LONGUEUR_MAX,
                           eval_data="modeles/laya_valid.jsonl"),
    )
    print(resume)

    # 3. Évaluation sur le jeu de test (val_clean.csv)
    agent = laya.load("modeles/laya")
    with Chrono() as c:
        probas = predire(agent, test["message"].tolist())
    evaluer("laya", test["label"], probas, c.duree, "cpu")
