"""
TP1 - Étape 2 : tableau comparatif des modèles

Usage : python -m model.comparer_modeles     (depuis la racine du projet)
Lit   : resultats/*.json (écrits par chaque script modele_*.py)
Écrit : resultats/comparaison.md (tableau au format Markdown, à coller dans le rapport)
"""

import json
from pathlib import Path

# Colonnes du tableau : (clé dans le fichier JSON, titre affiché)
COLONNES = [
    ("modele", "Modèle"),
    ("precision", "Précision"),
    ("rappel", "Rappel"),
    ("temps_par_requete_ms", "Temps par requête (ms)"),
    ("materiel", "Matériel"),
]

# 1. Lecture de tous les résultats (un fichier JSON par modèle)
resultats = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(Path("resultats").glob("*.json"))]
if not resultats:
    raise SystemExit("Aucun résultat : lancer d'abord les scripts modele_*.py")

# 2. Construction du tableau Markdown : ligne d'en-tête, ligne de séparation,
#    puis une ligne par modèle (triées par nom). Une valeur absente du JSON
#    (ancien format de résultat) donne une case vide au lieu d'une erreur.
lignes = ["| " + " | ".join(titre for _, titre in COLONNES) + " |",
          "|" + "---|" * len(COLONNES)]
for r in sorted(resultats, key=lambda r: r["modele"]):
    lignes.append("| " + " | ".join(str(r.get(cle, "")) for cle, _ in COLONNES) + " |")

# 3. Enregistrement et affichage
tableau = "\n".join(lignes)
Path("resultats/comparaison.md").write_text(tableau + "\n", encoding="utf-8")
print(tableau)
print("\nAttention : les temps ne sont comparables que mesurés sur le même matériel.")
