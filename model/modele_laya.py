# TP1 - Étape 2 : modèle de décision (Laya)
# Usage : python -m model.modele_laya     (depuis la racine du projet)

import json
import os
from pathlib import Path
os.environ.setdefault("USE_TF", "0")   # évite un blocage connu au chargement (doc Laya)
import numpy as np
import torch
import laya
from laya.train import TrainConfig, finetune, resolve_checkpoint_dir

from data_transformation.evaluation import (NB_NOTES, charger_donnees, evaluer,
                                            mesurer_temps_requete)

# ---------------------------------------------------------------------------
# PARAMÈTRES À MODIFIER
# ---------------------------------------------------------------------------
CHECKPOINT = "multilingual"   # le plus léger des modèles Laya (322 M de paramètres)
LONGUEUR_MAX = 128            # longueur max d'un texte, en tokens
# Nb de messages d'entraînement : réglé dans data_transformation/evaluation.py
# (NB_EXEMPLES_TRAIN), commun aux 3 modèles.
NB_EXEMPLES_VALID = 500       # nb de messages de validation pendant l'entraînement
EPOCHS = 1                  # nb de passages sur les données d'entraînement

# --- CONFIG CPU ---
APPAREIL = "cpu"              # force le CPU (pas de recherche de GPU)
NB_THREADS = torch.get_num_threads()   # nb de cœurs utilisés par PyTorch ; par défaut
                                       # = cœurs physiques (ne pas dépasser ce nombre)
# Calcul en précision réduite bf16 : plus rapide, MAIS seulement sur les processeurs
# compatibles (sinon le programme plante net, erreur 0xC000001D sous Windows).
# Laissé désactivé par sécurité.
PRECISION_BF16 = False
# ---------------------------------------------------------------------------

torch.set_num_threads(NB_THREADS)
if PRECISION_BF16:
    os.environ["LAYA_CPU_AMP"] = "bf16"

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
    print(f"Config : appareil={APPAREIL}, threads={NB_THREADS}, bf16={PRECISION_BF16}")
    train, valid, test = charger_donnees()

    # 1. Données au format Laya. "train" contient déjà les NB_EXEMPLES_TRAIN messages
    #    communs aux 3 modèles (voir charger_donnees) ; la validation est réduite
    #    à NB_EXEMPLES_VALID messages pour gagner du temps.
    Path("modeles").mkdir(exist_ok=True)
    preparer_jsonl(train, "modeles/laya_train.jsonl")
    preparer_jsonl(valid.sample(min(NB_EXEMPLES_VALID, len(valid)), random_state=42),
                   "modeles/laya_valid.jsonl")

    # 2. Entraînement (fine-tuning) de Laya sur nos données
    resume = finetune(
        data="modeles/laya_train.jsonl",
        model_dir=resolve_checkpoint_dir(CHECKPOINT),
        output_dir="modeles/laya",
        config=TrainConfig(epochs=EPOCHS, loss="soft-ce", max_len=LONGUEUR_MAX,
                           amp=False,   # pas de calcul 16 bits (réservé au GPU)
                           eval_data="modeles/laya_valid.jsonl"),
        device=APPAREIL,
    )
    print(resume)

    # 3. Évaluation sur le jeu de test (val_clean.csv)
    agent = laya.load("modeles/laya", device=APPAREIL)
    textes_test = test["message"].tolist()
    probas = predire(agent, textes_test)
    temps = mesurer_temps_requete(lambda t: predire(agent, [t]), textes_test)
    evaluer("laya", test["label"], probas, temps, APPAREIL)
