# TP1 - Étape 2 : modèle transformer (BERT-Mini)
# Usage : python -m model.modele_bert     (depuis la racine du projet)
#
# Principe : on part d'un BERT déjà entraîné par Google sur de grandes quantités
# de texte (il "comprend" déjà la langue), et on l'ajuste (fine-tuning) sur nos
# messages pour qu'il prédise une note de toxicité de 0 à 5.
#
# Sorties : modeles/bert/          (modèle entraîné, réutilisable par l'API)
#           resultats/bert.json    (précision, rappel, temps par requête)

import numpy as np
import torch
from sklearn.metrics import f1_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Code commun aux 3 modèles : mêmes données, mêmes métriques, même mesure du temps
from data_transformation.evaluation import (GRAINE, NB_NOTES, Chrono, charger_donnees, evaluer,
                        mesurer_temps_requete, poids_classes)

# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------
MODELE_BASE = "google/bert_uncased_L-4_H-256_A-4"   # BERT-Mini : 4 couches, 11 M de paramètres
DOSSIER_MODELE = "modeles/bert"                     # où le modèle entraîné est enregistré
LONGUEUR_MAX = 32          # en tokens : les messages font 3 mots en moyenne
TAILLE_LOT = 64            # nb de messages traités ensemble à chaque étape d'apprentissage
EPOCHS = 3                 # nb de passages complets sur les données d'entraînement
TAUX_APPRENTISSAGE = 1e-4  # taille des corrections ; un petit modèle supporte un taux
                           # plus élevé que BERT-base

# Graine fixe : mêmes résultats à chaque lancement (reproductibilité)
torch.manual_seed(GRAINE)
np.random.seed(GRAINE)


def lots(textes, labels, tokenizer, melanger):
    """
    Découpe les données en lots de TAILLE_LOT messages, tokenisés à la volée.

    Tokeniser = transformer le texte en numéros de tokens que BERT comprend
    ("noob" -> [CLS] noob [SEP] -> [101, 9152, 102]).
    padding=True   : complète les messages courts pour qu'ils aient tous la même longueur
    truncation=True : coupe les messages trop longs à LONGUEUR_MAX tokens
    melanger=True  : ordre aléatoire (entraînement) ; False : ordre d'origine (prédiction)
    """
    ordre = np.random.permutation(len(textes)) if melanger else np.arange(len(textes))
    for i in range(0, len(ordre), TAILLE_LOT):
        idx = ordre[i:i + TAILLE_LOT]
        entree = tokenizer([textes[j] for j in idx], padding=True, truncation=True,
                           max_length=LONGUEUR_MAX, return_tensors="pt")
        yield entree, torch.tensor(labels[idx])


def predire(modele, tokenizer, textes) -> np.ndarray:
    """Retourne, pour chaque message, les probabilités des 6 notes (0 à 5)."""
    modele.eval()                    # mode prédiction (désactive le dropout)
    sorties = []
    with torch.no_grad():            # pas d'apprentissage ici : plus rapide, moins de mémoire
        # les labels ne servent pas pour prédire : on passe des zéros
        for entree, _ in lots(textes, np.zeros(len(textes), dtype=int), tokenizer, False):
            # logits = 6 scores bruts ; softmax les transforme en probabilités (somme = 1)
            sorties.append(torch.softmax(modele(**entree).logits, dim=1))
    return torch.cat(sorties).numpy()


if __name__ == "__main__":
    # 0. Données : les mêmes pour les 3 modèles (voir charger_donnees)
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

    # 2. Perte pondérée : compense le déséquilibre des notes (81 % de 0).
    #    Sans poids, le modèle apprendrait à toujours répondre "0".
    perte = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(poids_classes(y_train), dtype=torch.float32))
    # AdamW : algorithme qui corrige les poids du réseau à chaque étape
    optimiseur = torch.optim.AdamW(modele.parameters(), lr=TAUX_APPRENTISSAGE)

    # 3. Entraînement (fine-tuning) ; on garde le meilleur epoch selon la validation
    meilleur_f1 = -1
    with Chrono() as chrono_entrainement:
        for epoch in range(1, EPOCHS + 1):
            modele.train()                      # mode entraînement (dropout actif)
            for n, (entree, y) in enumerate(lots(textes_train, y_train, tokenizer, True)):
                optimiseur.zero_grad()          # efface les corrections du lot précédent
                l = perte(modele(**entree).logits, y)   # erreur sur ce lot
                l.backward()                    # calcule comment corriger chaque poids
                optimiseur.step()               # applique les corrections
                if n % 100 == 0:
                    print(f"  epoch {epoch}, lot {n} : perte = {l.item():.4f}")

            # Fin d'epoch : F1 sur la validation (toxique = note >= 1)
            p_valid = predire(modele, tokenizer, textes_valid)
            f1_valid = f1_score(valid["label"].values >= 1, (1 - p_valid[:, 0]) >= 0.5)
            print(f"epoch {epoch} : F1 validation (toxique / non toxique) = {f1_valid:.4f}")
            # On n'enregistre le modèle que s'il est meilleur que les epochs précédents
            # (évite de garder un modèle qui a commencé à apprendre par cœur)
            if f1_valid > meilleur_f1:
                meilleur_f1 = f1_valid
                modele.save_pretrained(DOSSIER_MODELE)
                tokenizer.save_pretrained(DOSSIER_MODELE)
    print(f"Durée d'entraînement : {chrono_entrainement.duree:.0f} s")

    # 4. Évaluation du meilleur modèle sur le jeu d'évaluation (val_clean.csv)
    modele = AutoModelForSequenceClassification.from_pretrained(DOSSIER_MODELE)
    textes_test = test["message"].tolist()
    probas = predire(modele, tokenizer, textes_test)          # pour précision et rappel
    # Temps de traitement d'UNE requête (messages envoyés un par un, comme l'API)
    temps = mesurer_temps_requete(lambda t: predire(modele, tokenizer, [t]), textes_test)
    evaluer("bert", test["label"], probas, temps, "cpu")
