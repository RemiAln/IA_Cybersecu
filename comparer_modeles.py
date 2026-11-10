"""
TP1 - Étape 2 : tableau comparatif des modèles

Usage : python comparer_modeles.py
Lit   : resultats/*.json (écrits par chaque script modele_*.py)
Écrit : resultats/comparaison.md
"""

import json
from pathlib import Path

COLONNES = [
    ("modele", "Modèle"),
    ("precision", "Précision"),
    ("rappel", "Rappel"),
    ("f1", "F1"),
    ("f1_macro_6_notes", "F1 macro (6 notes)"),
    ("erreur_moyenne_score", "Erreur moy. score /100"),
    ("temps_par_message_ms", "Temps / message (ms)"),
    ("materiel", "Matériel"),
]

resultats = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(Path("resultats").glob("*.json"))]
if not resultats:
    raise SystemExit("Aucun résultat : lancer d'abord les scripts modele_*.py")

lignes = ["| " + " | ".join(titre for _, titre in COLONNES) + " |",
          "|" + "---|" * len(COLONNES)]
for r in sorted(resultats, key=lambda r: -r["f1"]):
    lignes.append("| " + " | ".join(str(r.get(cle, "")) for cle, _ in COLONNES) + " |")

tableau = "\n".join(lignes)
Path("resultats/comparaison.md").write_text(tableau + "\n", encoding="utf-8")
print(tableau)
print("\nAttention : les temps ne sont comparables que mesurés sur le même matériel.")
