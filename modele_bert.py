"""
TP1 - Étape 2 : modèle transformer, BERT multilingue (fine-tuning)

Usage : python modele_bert.py            (GPU fortement conseillé)
Écrit : modeles/bert/, resultats/bert.json

On part d'un BERT déjà pré-entraîné sur Wikipédia en 104 langues, et on
l'ajuste ("fine-tuning") pour prédire la note de toxicité 0-5.
Choix de distilbert-base-multilingual-cased :
  - multilingue : les messages sont en anglais, russe, polonais, tchèque...
  - "cased" : garde les majuscules ("STOP" crié n'est pas "stop")
  - version distillée : 40 % plus petite et ~2x plus rapide que BERT-base,
    pour une précision proche ; la latence comptera à l'étape 5 (montée en charge).
"""

import os
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          get_linear_schedule_with_warmup)

from evaluation import (GRAINE, NB_NOTES, Chrono, charger_donnees, evaluer,
                        poids_classes)
from nettoyage import nettoyer_transformer

torch.manual_seed(GRAINE)
APPAREIL = "cuda" if torch.cuda.is_available() else "cpu"

MODELE_BASE = os.environ.get("MODELE_BERT", "distilbert-base-multilingual-cased")
LONGUEUR_MAX = 64        # en tokens ; les messages font 30 mots au maximum
TAILLE_LOT = 32
EPOCHS = int(os.environ.get("EPOCHS_BERT", 3))
TAUX_APPRENTISSAGE = 3e-5   # petit : on ajuste un modèle déjà entraîné, on ne le refait pas


def lots(textes, labels, tokenizer, melanger):
    """Découpe en lots et tokenise à la volée."""
    ordre = np.random.permutation(len(textes)) if melanger else np.arange(len(textes))
    for i in range(0, len(ordre), TAILLE_LOT):
        idx = ordre[i:i + TAILLE_LOT]
        entree = tokenizer([textes[j] for j in idx], padding=True, truncation=True,
                           max_length=LONGUEUR_MAX, return_tensors="pt")
        yield {k: v.to(APPAREIL) for k, v in entree.items()}, torch.tensor(labels[idx]).to(APPAREIL)


def predire(modele, tokenizer, textes) -> np.ndarray:
    modele.eval()
    sorties = []
    with torch.no_grad(), torch.autocast(APPAREIL, enabled=APPAREIL == "cuda"):
        for entree, _ in lots(textes, np.zeros(len(textes), dtype=int), tokenizer, False):
            sorties.append(torch.softmax(modele(**entree).logits.float(), dim=1).cpu())
    return torch.cat(sorties).numpy()


if __name__ == "__main__":
    np.random.seed(GRAINE)
    train, valid, test = charger_donnees()
    textes = {nom: df["message"].map(nettoyer_transformer).tolist()
              for nom, df in [("train", train), ("valid", valid)]}
    y_train = train["label"].values

    print(f"Modèle de départ : {MODELE_BASE} (appareil : {APPAREIL})")
    tokenizer = AutoTokenizer.from_pretrained(MODELE_BASE)
    # Les balises <USER>, <PERSON>... deviennent des tokens entiers au lieu
    # d'être découpées en "<", "PER", "##SON", ">"
    tokenizer.add_tokens(["<USER>", "<PERSON>", "<URL>", "<EMAIL>", "<IP>", "<PHONE>"])
    modele = AutoModelForSequenceClassification.from_pretrained(MODELE_BASE, num_labels=NB_NOTES)
    modele.resize_token_embeddings(len(tokenizer))
    modele.to(APPAREIL)

    perte = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(poids_classes(y_train), dtype=torch.float32).to(APPAREIL))
    optimiseur = torch.optim.AdamW(modele.parameters(), lr=TAUX_APPRENTISSAGE, weight_decay=0.01)
    nb_etapes = EPOCHS * int(np.ceil(len(y_train) / TAILLE_LOT))
    planning = get_linear_schedule_with_warmup(optimiseur, int(0.06 * nb_etapes), nb_etapes)
    echelle = torch.amp.GradScaler(enabled=APPAREIL == "cuda")   # calcul en 16 bits sur GPU

    meilleur_f1 = -1
    for epoch in range(1, EPOCHS + 1):
        modele.train()
        for n, (entree, y) in enumerate(lots(textes["train"], y_train, tokenizer, True)):
            optimiseur.zero_grad()
            with torch.autocast(APPAREIL, enabled=APPAREIL == "cuda"):
                l = perte(modele(**entree).logits.float(), y)
            echelle.scale(l).backward()
            echelle.unscale_(optimiseur)
            torch.nn.utils.clip_grad_norm_(modele.parameters(), 1.0)
            echelle.step(optimiseur)
            echelle.update()
            planning.step()
            if n % 200 == 0:
                print(f"  epoch {epoch}, lot {n} : perte = {l.item():.4f}")

        p_valid = predire(modele, tokenizer, textes["valid"])
        f1_valid = f1_score(valid["label"].values >= 1, (1 - p_valid[:, 0]) >= 0.5)
        print(f"epoch {epoch} : F1 validation = {f1_valid:.4f}")
        # On ne garde que le meilleur epoch
        if f1_valid > meilleur_f1:
            meilleur_f1 = f1_valid
            modele.save_pretrained("modeles/bert")
            tokenizer.save_pretrained("modeles/bert")

    # Évaluation du meilleur modèle sur le test (nettoyage compris dans le chrono)
    modele = AutoModelForSequenceClassification.from_pretrained("modeles/bert").to(APPAREIL)
    with Chrono() as c:
        probas = predire(modele, tokenizer, test["message"].map(nettoyer_transformer).tolist())
        if APPAREIL == "cuda":
            torch.cuda.synchronize()
    materiel = torch.cuda.get_device_name(0) if APPAREIL == "cuda" else "cpu"
    evaluer("bert", test["label"], probas, c.duree, materiel)
