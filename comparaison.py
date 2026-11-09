"""
TP1 - Étape 1 : comparaison version initiale / version anonymisée

Usage : python comparaison.py
Lit   : data_*/..._raw.csv et data_*/..._anon.csv   (LECTURE SEULE, rien n'est écrit)
"""

import re
from collections import Counter

import pandas as pd

PAIRES = [
    ("data_train/train_raw.csv", "data_train/train_anon.csv"),
    ("data_eval/val_raw.csv", "data_eval/val_anon.csv"),
]
BALISES = ["<EMAIL>", "<URL>", "<IP>", "<PHONE>", "<PERSON>"]
NB_EXEMPLES = 10   # exemples affichés par balise

# Recherche de données personnelles RESTANTES dans la version anonymisée
# (vérifie que l'anonymisation n'a rien oublié de ce qu'elle devait traiter)
RESIDUS = {
    "e-mail": r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}",
    "url": r"https?://|www\.[\w-]+\.",
    "ipv4": r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
    "téléphone (+indicatif)": r"\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}",
}


def mots(texte):
    return re.findall(r"\w+", str(texte).lower())


for chemin_raw, chemin_anon in PAIRES:
    raw = pd.read_csv(chemin_raw)
    anon = pd.read_csv(chemin_anon)
    print("=" * 70)
    print(f"{chemin_raw}  vs  {chemin_anon}")
    print("=" * 70)

    # 1. Intégrité : l'anonymisation ne doit ni supprimer ni déplacer de lignes,
    #    ni toucher aux labels
    print("\n1. Intégrité")
    print(f"  lignes          : {len(raw)} -> {len(anon)}")
    print(f"  colonnes        : {list(raw.columns)} -> {list(anon.columns)}")
    print(f"  index identique : {raw['index'].equals(anon['index'])}")
    if "label" in raw:
        print(f"  label identique : {raw['label'].equals(anon['label'])}")

    # 2. Volume modifié
    modifie = raw["message"].astype(str) != anon["message"].astype(str)
    print("\n2. Messages modifiés")
    print(f"  {modifie.sum()} / {len(raw)}  ({modifie.mean():.2%})")
    print("  par balise (nb de messages contenant la balise) :")
    for b in BALISES:
        print(f"    {b:9} {anon['message'].astype(str).str.contains(b, regex=False).sum()}")

    # 3. Les messages modifiés sont-ils plutôt toxiques ou non ?
    #    (vérifie que l'anonymisation ne biaise pas une classe en particulier)
    if "label" in raw:
        print("\n3. Répartition des labels : tous les messages vs messages modifiés")
        rep = pd.DataFrame({
            "tous": raw["label"].value_counts(normalize=True),
            "modifiés": raw.loc[modifie, "label"].value_counts(normalize=True),
        }).fillna(0).sort_index()
        print((rep * 100).round(1).astype(str).add(" %").to_string())

    # 4. Mots qui ont disparu : ce que l'anonymisation a réellement remplacé.
    #    C'est ici qu'on repère les FAUX POSITIFS (un mot normal remplacé à tort).
    disparus = Counter()
    for avant, apres in zip(raw.loc[modifie, "message"], anon.loc[modifie, "message"]):
        disparus.update(Counter(mots(avant)) - Counter(mots(apres)))
    print("\n4. Mots remplacés les plus fréquents (repérer les faux positifs) :")
    for mot, n in disparus.most_common(30):
        print(f"    {n:4}  {mot}")

    # 5. Exemples avant / après, par type de donnée
    print("\n5. Exemples avant / après")
    for b in BALISES:
        lignes = anon["message"].astype(str).str.contains(b, regex=False)
        if lignes.any():
            print(f"\n  --- {b} ---")
            for avant, apres in zip(raw.loc[lignes, "message"].head(NB_EXEMPLES),
                                    anon.loc[lignes, "message"].head(NB_EXEMPLES)):
                print(f"    AVANT : {avant}")
                print(f"    APRÈS : {apres}")

    # 6. Données personnelles encore présentes après anonymisation
    print("\n6. Résidus détectés dans la version anonymisée")
    for nom, motif in RESIDUS.items():
        restes = anon["message"].astype(str).str.contains(motif, regex=True)
        print(f"    {nom:24} {restes.sum()}")
        for m in anon.loc[restes, "message"].head(3):
            print(f"        ex : {m}")
    print()
