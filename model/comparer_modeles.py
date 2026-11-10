"""
TP1 - Étape 2 : tableau comparatif des modèles

Usage : python -m model.comparer_modeles     (depuis la racine du projet)
Lit   : resultats/*.json (écrits par chaque script modele_*.py)
Écrit : resultats/comparaison.md
"""

import json
from pathlib import Path

COLONNES = [
    ("modele", "Modèle"),
    ("precision", "Précision"),
    ("rappel", "Rappel"),
    ("temps_par_requete_ms", "Temps par requête (ms)"),
    ("materiel", "Matériel"),
]

resultats = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(Path("resultats").glob("*.json"))]
if not resultats:
    raise SystemExit("Aucun résultat : lancer d'abord les scripts modele_*.py")

lignes = ["| " + " | ".join(titre for _, titre in COLONNES) + " |",
          "|" + "---|" * len(COLONNES)]
for r in sorted(resultats, key=lambda r: r["modele"]):
    lignes.append("| " + " | ".join(str(r.get(cle, "")) for cle, _ in COLONNES) + " |")

tableau = "\n".join(lignes)
Path("resultats/comparaison.md").write_text(tableau + "\n", encoding="utf-8")
print(tableau)
print("\nAttention : les temps ne sont comparables que mesurés sur le même matériel.")
