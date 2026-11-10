# TP1 - Étape 2 : code commun aux 3 modèles (découpage des données, métriques)
# Ce fichier ne se lance pas seul : il est importé par les scripts de model/.

import json
import statistics
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score
from sklearn.model_selection import train_test_split

GRAINE = 42                  # même découpage et même initialisation à chaque lancement
NB_NOTES = 6                 # notes de toxicité 0 à 5

# Nombre de messages d'entraînement, IDENTIQUE pour les 3 modèles (benchmark équitable).
# None = tout le jeu d'entraînement.
NB_EXEMPLES_TRAIN = 5000
DOSSIER_RESULTATS = Path("resultats")
NB_REQUETES_TEST = 100       # nb de messages envoyés un par un pour mesurer le temps par requête


def charger_donnees():
    """
    Retourne (train, valid, test), trois DataFrames avec "message" et "label" (entier 0-5).

    - test  = data_eval/val_clean.csv, jamais vu pendant l'entraînement :
              c'est sur lui qu'on compare les trois modèles.
    - valid = 10 % de data_train, tiré en gardant la proportion de chaque note :
              sert à choisir le meilleur epoch.
    - train = NB_EXEMPLES_TRAIN messages tirés dans les 90 % restants, en gardant
              la proportion de chaque note. Avec la graine fixe, ce sont TOUJOURS
              les mêmes messages, pour les 3 modèles et à chaque lancement.
    """
    # Fichiers nettoyés par nettoyage.py. keep_default_na=False : sinon pandas
    # transforme des messages comme "nan", "null" ou "na" en valeur manquante.
    train = pd.read_csv("data_train/train_clean.csv", keep_default_na=False)
    test = pd.read_csv("data_eval/val_clean.csv", keep_default_na=False)
    for df in (train, test):
        df["message"] = df["message"].astype(str)
        df["label"] = df["label"].astype(int)
    train, valid = train_test_split(train, test_size=0.10, stratify=train["label"],
                                    random_state=GRAINE)
    if NB_EXEMPLES_TRAIN is not None and NB_EXEMPLES_TRAIN < len(train):
        train, _ = train_test_split(train, train_size=NB_EXEMPLES_TRAIN,
                                    stratify=train["label"], random_state=GRAINE)
    print(f"Données : {len(train)} messages d'entraînement, {len(valid)} de validation, "
          f"{len(test)} d'évaluation")
    return train.reset_index(drop=True), valid.reset_index(drop=True), test


def poids_classes(labels) -> np.ndarray:
    """
    Poids de chaque note dans la fonction de perte.
    Le dataset est très déséquilibré (81 % de 0, 24 messages notés 5). Sans poids,
    un modèle qui répond toujours 0 a déjà 81 % de bonnes réponses.
    On prend 1 / racine(fréquence) plutôt que 1 / fréquence : avec 24 exemples,
    un poids 1 400 fois plus fort que la note 0 rendrait l'entraînement instable.
    """
    comptes = np.bincount(labels, minlength=NB_NOTES).astype(float)
    poids = 1.0 / np.sqrt(np.maximum(comptes, 1))
    return poids / poids.mean()


def score_toxicite(probas: np.ndarray) -> np.ndarray:
    """
    Score 0-100 = note moyenne attendue x 20.
    Ex : P(0)=0.5, P(2)=0.5 -> note attendue 1 -> score 20.
    Plus juste que "note la plus probable x 20" : le score bouge en continu
    quand le modèle hésite.
    """
    return probas @ np.arange(NB_NOTES) * (100 / (NB_NOTES - 1))


def mesurer_temps_requete(predire_un, textes, n=NB_REQUETES_TEST) -> float:
    """
    Temps de traitement d'UNE requête, en millisecondes (médiane sur n messages).

    Les messages sont envoyés un par un, comme dans l'API, et non par lots :
    c'est ce temps que ressent l'utilisateur. On prend la médiane plutôt que la
    moyenne pour ne pas être faussé par un appel ralenti par Windows.
    predire_un : fonction qui prend UN texte et renvoie sa prédiction.
    """
    predire_un(textes[0])               # échauffement (1er appel plus lent), non compté
    durees = []
    for texte in textes[:n]:
        debut = time.perf_counter()
        predire_un(texte)
        durees.append((time.perf_counter() - debut) * 1000)
    return statistics.median(durees)


def evaluer(nom: str, labels, probas: np.ndarray, temps_requete_ms: float, materiel: str) -> dict:
    """
    Calcule les métriques sur le jeu de test et les enregistre dans resultats/<nom>.json.

    Un message est jugé toxique si sa note est >= 1. Côté modèle, il est prédit
    toxique si P(note >= 1) >= 0.5.
    """
    labels = np.asarray(labels)
    vrai_toxique = labels >= 1
    predit_toxique = (1 - probas[:, 0]) >= 0.5

    resultats = {
        "modele": nom,
        "precision": round(precision_score(vrai_toxique, predit_toxique, zero_division=0), 4),
        "rappel": round(recall_score(vrai_toxique, predit_toxique, zero_division=0), 4),
        # temps de traitement d'une requête (un message), en millisecondes
        "temps_par_requete_ms": round(temps_requete_ms, 2),
        "materiel": materiel,
    }
    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    (DOSSIER_RESULTATS / f"{nom}.json").write_text(json.dumps(resultats, indent=2,
                                                               ensure_ascii=False))
    print(json.dumps(resultats, indent=2, ensure_ascii=False))
    return resultats


class Chrono:
    """with Chrono() as c: ...   puis c.duree contient le temps écoulé en secondes."""
    def __enter__(self):
        self.debut = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.duree = time.perf_counter() - self.debut
