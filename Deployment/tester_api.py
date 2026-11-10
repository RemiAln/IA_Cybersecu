"""
TP1 - Étape 3 : envoie quelques requêtes à l'API et affiche les réponses.

Usage : python Deployment/tester_api.py                          (API locale)
        python Deployment/tester_api.py https://xxxx.run.app     (API déployée sur Cloud Run)
"""

import json
import sys
import time
import urllib.error
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")

EXEMPLES = [
    "gg wp team",                       # sain
    "nice shot, well played",           # sain
    "useless noob",                     # insulte légère
    "you are so stupid, uninstall",     # insulte
    "kys idiot",                        # très toxique
    "",                                 # invalide : texte vide -> erreur 422 attendue
]


def envoyer(texte):
    requete = urllib.request.Request(
        f"{URL}/score",
        data=json.dumps({"texte": texte}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    debut = time.perf_counter()
    try:
        with urllib.request.urlopen(requete) as r:
            code, corps = r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        code, corps = e.code, json.loads(e.read())
    return code, corps, (time.perf_counter() - debut) * 1000


if __name__ == "__main__":
    print(f"API testée : {URL}\n")
    for texte in EXEMPLES:
        code, corps, ms = envoyer(texte)
        print(f"{texte!r:35} -> HTTP {code}  ({ms:.0f} ms)")
        print(f"    {json.dumps(corps, ensure_ascii=False)}")
