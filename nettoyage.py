import re
from pathlib import Path

import pandas as pd

FICHIERS = [
    "data_train/train_anon.csv",
    "data_eval/val_anon.csv",
]

# ---------------------------------------------------------------------------
# 1. Règles de nettoyage
# ---------------------------------------------------------------------------

# Balises de l'étape 1 -> jetons fixes, sans ponctuation.
# Sans ça, le retrait de la ponctuation transformerait "<PERSON>" en "person"
# (confondu avec le mot anglais) et "<USER_a3f2c91b>" en un mot différent pour
# chaque joueur. Le modèle n'a besoin de savoir que "un joueur est visé".
BALISES = [
    (re.compile(r"<USER_[0-9a-fA-F]+>"), " xxuser "),
    (re.compile(r"<PERSON>"), " xxperson "),
    (re.compile(r"<URL>"), " xxurl "),
    (re.compile(r"<EMAIL>"), " xxemail "),
    (re.compile(r"<IP>"), " xxip "),
    (re.compile(r"<PHONE>"), " xxphone "),
]

# Tout ce qui n'est ni une lettre (tous alphabets : latin, cyrillique...), ni un
# chiffre, ni un espace = ponctuation, symbole OU emoji
# -> remplacé par un espace. Les emojis disparaissent donc avec la ponctuation.
# "_" est ajouté explicitement : \w le considère comme une lettre, sinon il
# resterait des jetons comme "_" ou "____" (les jetons xxuser... n'en ont pas).
PONCTUATION_RE = re.compile(r"[^\w\s]|_")


def nettoyer(texte: str) -> str:
    texte = str(texte)

    # 1. Balises de l'étape 1 -> jetons fixes
    for motif, jeton in BALISES:
        texte = motif.sub(jeton, texte)

    # 2. Casse : tout en minuscules (casefold gère aussi le cyrillique, l'allemand...)
    texte = texte.casefold()

    # 3. Ponctuation et emojis
    texte = PONCTUATION_RE.sub(" ", texte)

    # 4. Espaces multiples -> un seul
    return re.sub(r"\s+", " ", texte).strip()


# ---------------------------------------------------------------------------
# 2. Application aux fichiers du dataset
# ---------------------------------------------------------------------------

def chemin_sortie(chemin_entree: str) -> Path:
    """data_eval/val_anon.csv -> data_eval/val_clean.csv (même dossier)."""
    entree = Path(chemin_entree)
    sortie = entree.with_name(entree.name.replace("_anon", "_clean"))
    # Sécurité : on refuse d'écraser le fichier source
    if sortie.resolve() == entree.resolve():
        raise ValueError(f"Le fichier de sortie écraserait la source : {entree}")
    return sortie


if __name__ == "__main__":
    for chemin in FICHIERS:
        df = pd.read_csv(chemin)
        df["message_clean"] = df["message"].apply(nettoyer)

        # Statistiques avant / après
        vocab_avant = set(" ".join(df["message"].astype(str)).split())
        vocab_apres = set(" ".join(df["message_clean"]).split())
        vides = (df["message_clean"] == "").sum()
        doublons = df["message_clean"].duplicated().sum()

        print(f"\n=== {chemin} : {len(df)} messages")
        print(f"  vocabulaire : {len(vocab_avant)} -> {len(vocab_apres)} mots distincts")
        print(f"  messages vides après nettoyage : {vides}  (ex : '???', '!!!')")
        print(f"  doublons après nettoyage       : {doublons}")
        print("  exemples :")
        for avant, apres in df[["message", "message_clean"]].sample(10, random_state=0).values:
            print(f"    AVANT : {avant}\n    APRÈS : {apres}")

        # Suppression des messages devenus vides (":)", "?", "***"...) : sans
        # texte, le modèle n'a rien à apprendre. Les doublons sont gardés.
        est_vide = df["message_clean"] == ""
        if "label" in df:
            print("  labels des messages vides supprimés :",
                  df.loc[est_vide, "label"].value_counts().sort_index().to_dict())
        print("  exemples supprimés :", df.loc[est_vide, "message"].head(8).tolist())
        df = df[~est_vide].copy()

        # Sauvegarde : on remplace la colonne d'origine par la version nettoyée.
        df["message"] = df["message_clean"]
        sortie = chemin_sortie(chemin)
        df.drop(columns="message_clean").to_csv(sortie, index=False)
        print(f"  -> écrit : {sortie} ({len(df)} messages)")
