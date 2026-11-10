# TP1 - Étape 2 : modèle transformer (BERT-Mini)
# Usage : python -m model.modele_bert     (depuis la racine du projet)

import numpy as np
import torch
from sklearn.metrics import f1_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from data_transformation.evaluation import (GRAINE, NB_NOTES, Chrono, charger_donnees, evaluer,
                        mesurer_temps_requete, poids_classes)

MODELE_BASE = "google/bert_uncased_L-4_H-256_A-4"   # BERT-Mini
DOSSIER_MODELE = "modeles/bert"
LONGUEUR_MAX = 32          # en tokens : les messages font 3 mots en moyenne
TAILLE_LOT = 64
EPOCHS = 3
TAUX_APPRENTISSAGE = 1e-4  # un petit modèle supporte un taux plus élevé que BERT-base

torch.manual_seed(GRAINE)
np.random.seed(GRAINE)


def lots(textes, labels, tokenizer, melanger):
    """Découpe les données en lots de TAILLE_LOT messages, tokenisés à la volée."""
    ordre = np.random.permutation(len(textes)) if melanger else np.arange(len(textes))
    for i in range(0, len(ordre), TAILLE_LOT):
        idx = ordre[i:i + TAILLE_LOT]
        entree = tokenizer([textes[j] for j in idx], padding=True, truncation=True,
                           max_length=LONGUEUR_MAX, return_tensors="pt")
        yield entree, torch.tensor(labels[idx])


def predire(modele, tokenizer, textes) -> np.ndarray:
    """Retourne, pour chaque message, les probabilités des 6 notes (0 à 5)."""
    modele.eval()
    sorties = []
    with torch.no_grad():
        for entree, _ in lots(textes, np.zeros(len(textes), dtype=int), tokenizer, False):
            sorties.append(torch.softmax(modele(**entree).logits, dim=1))
    return torch.cat(sorties).numpy()


if __name__ == "__main__":
    train, valid, test = charger_donnees()
    textes_train = train["message"].tolist()
    textes_valid = valid["message"].tolist()
    y_train = train["label"].values

    # 1. Chargement du modèle pré-entraîné, avec une nouvelle tête de
    #    classification à 6 sorties (une par note de toxicité)
    print(f"Modèle de départ : {MODELE_BASE}")
    tokenizer = AutoTokenizer.from_pretrained(MODELE_BASE)
    modele = AutoModelForSequenceClassification.from_pretrained(MODELE_BASE,
                                                               num_labels=NB_NOTES)

    # 2. Perte pondérée : compense le déséquilibre des notes (81 % de 0)
    perte = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(poids_classes(y_train), dtype=torch.float32))
    optimiseur = torch.optim.AdamW(modele.parameters(), lr=TAUX_APPRENTISSAGE)

    # 3. Entraînement (fine-tuning) ; on garde le meilleur epoch selon la validation
    meilleur_f1 = -1
    with Chrono() as chrono_entrainement:
        for epoch in range(1, EPOCHS + 1):
            modele.train()
            for n, (entree, y) in enumerate(lots(textes_train, y_train, tokenizer, True)):
                optimiseur.zero_grad()
                l = perte(modele(**entree).logits, y)
                l.backward()
                optimiseur.step()
                if n % 100 == 0:
                    print(f"  epoch {epoch}, lot {n} : perte = {l.item():.4f}")

            p_valid = predire(modele, tokenizer, textes_valid)
            f1_valid = f1_score(valid["label"].values >= 1, (1 - p_valid[:, 0]) >= 0.5)
            print(f"epoch {epoch} : F1 validation (toxique / non toxique) = {f1_valid:.4f}")
            if f1_valid > meilleur_f1:
                meilleur_f1 = f1_valid
                modele.save_pretrained(DOSSIER_MODELE)
                tokenizer.save_pretrained(DOSSIER_MODELE)
    print(f"Durée d'entraînement : {chrono_entrainement.duree:.0f} s")

    # 4. Évaluation du meilleur modèle sur le jeu de test (val_clean.csv)
    modele = AutoModelForSequenceClassification.from_pretrained(DOSSIER_MODELE)
    textes_test = test["message"].tolist()
    probas = predire(modele, tokenizer, textes_test)
    temps = mesurer_temps_requete(lambda t: predire(modele, tokenizer, [t]), textes_test)
    evaluer("bert", test["label"], probas, temps, "cpu")
