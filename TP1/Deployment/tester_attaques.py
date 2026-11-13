"""
TP1 - Étape 6 : simulation d'attaques sur l'API (grille de tests S8, S9, S11 + validation)

Usage : API_KEY=la_vraie_cle python Deployment/tester_attaques.py http://<IP>

La vraie clé est obligatoire : sans elle, toutes les requêtes de S8 et S9 seraient
refusées (401) avant d'atteindre le modèle, et ces tests ne vérifieraient rien.
Affiche le résultat de chaque attaque, à recopier dans la grille de tests.
"""

import json
import os
import sys
import urllib.error
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
VRAIE_CLE = os.environ.get("API_KEY", "")

if not VRAIE_CLE:
    sys.exit("Définir API_KEY (la vraie clé) : sans elle, S8 et S9 renvoient 401 et ne testent rien.")


def envoyer(texte, cle=VRAIE_CLE):
    """Envoie un texte à /score ; renvoie (code HTTP, réponse JSON ou None)."""
    entetes = {"Content-Type": "application/json"}
    if cle:
        entetes["X-API-Key"] = cle
    requete = urllib.request.Request(f"{URL}/score", data=json.dumps({"texte": texte}).encode(),
                                     headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:                      # API injoignable, délai dépassé...
        return f"erreur ({type(e).__name__})", None


def afficher(texte, code, rep):
    score = f"score {rep['score']:5.1f}  toxique={rep['toxique']}" if rep else ""
    print(f"  {str(texte)[:38]!r:40} -> HTTP {code}  {score}")


print(f"API testée : {URL}\n")

# S8 : injection. L'API doit traiter ces textes comme du texte normal (200),
# sans planter (500) ni exécuter quoi que ce soit.
print("=== S8 : tentatives d'injection ===")
for texte in ["<script>alert(1)</script>",
              "'; DROP TABLE users; --",
              "{{7*7}} ${7*7}",
              "../../etc/passwd"]:
    afficher(texte, *envoyer(texte))

# S9 : contournement du modèle. On compare une insulte et ses versions déguisées :
# si le score chute, le modèle se laisse tromper.
print("\n=== S9 : insultes déguisées (comparer les scores) ===")
for texte in ["idiot", "1d10t", "i d i o t", "id1ot",
              "noob", "n00b",
              "stupid", "stup1d", "s.t.u.p.i.d"]:
    afficher(texte, *envoyer(texte))

# Validation des entrées : texte trop long (tentative de saturer le modèle),
# vide, ou du mauvais type. Attendu : 422 partout, jamais 500.
print("\n=== Validation des entrées (attendu : 422, jamais 500) ===")
for texte in ["a" * 1001, "", 12345, None]:
    afficher(texte, *envoyer(texte))

# S11 : essais de clés au hasard. Toutes doivent être refusées (401).
print("\n=== S11 : 20 requêtes avec de fausses clés API ===")
codes = {}
for i in range(20):
    code, _ = envoyer("gg wp", cle=f"fausse-cle-{i}")
    codes[code] = codes.get(code, 0) + 1
print(f"  codes reçus : {codes}")
acceptees = codes.get(200, 0)
if codes.get(401) == 20:
    print("  -> OK : toutes les fausses clés ont été refusées")
    print("     (mais aucun blocage après plusieurs échecs : pas de limitation du nombre d'essais)")
elif acceptees:
    print(f"  -> FAILLE : {acceptees} fausse(s) clé(s) acceptée(s) : l'API ne vérifie pas la clé")
else:
    print("  -> résultat inattendu : vérifier que l'API est joignable")
