"""
TP1 - Étape 2 : modèle de décision, Laya

Usage : python modele_laya.py zeroshot    évalue Laya tel quel, sans entraînement
        python modele_laya.py finetune    l'ajuste sur nos données puis l'évalue
Écrit : resultats/laya_zeroshot.json, resultats/laya_finetune.json, modeles/laya_finetune/

Laya ne génère pas de texte : on lui pose une question typée et il renvoie une
probabilité pour chaque réponse possible. On utilise une question "score" à 6
niveaux, qui correspond directement à nos notes 0 à 5.
On prend le checkpoint multilingue, car les messages ne sont pas tous en anglais.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_TF", "0")   # évite un blocage connu au chargement (doc Laya)

import numpy as np

import laya
from evaluation import NB_NOTES, Chrono, charger_donnees, evaluer
from nettoyage import nettoyer_transformer

CHECKPOINT = "multilingual"
NB_EXEMPLES_FT = int(os.environ.get("NB_EXEMPLES_LAYA", 10000))

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
    reponses = agent.predict_batch(textes, QUESTIONS, batch_size=64)
    return np.array([[r["answers"]["toxicite"]["probabilities"][str(k)] for k in range(NB_NOTES)]
                     for r in reponses])


def evaluer_agent(agent, nom, test):
    import torch
    with Chrono() as c:
        probas = predire(agent, test["message"].map(nettoyer_transformer).tolist())
    materiel = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    evaluer(nom, test["label"], probas, c.duree, materiel)


def preparer_jsonl(df, chemin):
    """Format attendu par laya.train : une ligne {state, questions, expected} par message."""
    with open(chemin, "w", encoding="utf-8") as f:
        for texte, note in zip(df["message"].map(nettoyer_transformer), df["label"]):
            f.write(json.dumps({"state": texte, "questions": QUESTIONS,
                                "expected": {"toxicite": int(note)}}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "zeroshot"
    train, valid, test = charger_donnees()

    if mode == "zeroshot":
        evaluer_agent(laya.load("convaiinnovations/laya", subfolder=CHECKPOINT),
                      "laya_zeroshot", test)

    elif mode == "finetune":
        from laya.train import TrainConfig, finetune, resolve_checkpoint_dir

        # Laya est ~10x plus lourd que DistilBERT : on l'ajuste sur un sous-ensemble
        # tiré au hasard (même répartition des notes que le jeu complet)
        echantillon = train.groupby("label", group_keys=False).apply(
            lambda g: g.sample(frac=min(1, NB_EXEMPLES_FT / len(train)), random_state=42))
        Path("modeles").mkdir(exist_ok=True)
        preparer_jsonl(echantillon, "modeles/laya_train.jsonl")
        preparer_jsonl(valid, "modeles/laya_valid.jsonl")

        resume = finetune(
            data="modeles/laya_train.jsonl",
            model_dir=resolve_checkpoint_dir(CHECKPOINT),
            output_dir="modeles/laya_finetune",
            # soft-ce : perte d'entropie croisée simple ; la doc Laya n'a mesuré
            # aucun gain avec la perte "rlcd" par défaut
            config=TrainConfig(epochs=2, loss="soft-ce", eval_data="modeles/laya_valid.jsonl"),
        )
        print(resume)
        evaluer_agent(laya.load("modeles/laya_finetune"), "laya_finetune", test)
    else:
        sys.exit("mode inconnu : zeroshot ou finetune")
