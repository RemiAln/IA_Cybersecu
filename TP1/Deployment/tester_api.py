"""
TP1 - Étape 3 : envoie quelques requêtes à l'API et affiche les réponses.

Sert à produire le livrable "exemples de requêtes et réponses", et à vérifier
que l'API fonctionne (en local, dans Docker ou sur GKE).

Usage : python Deployment/tester_api.py <URL> <CLE_API>
  ex :  python Deployment/tester_api.py http://127.0.0.1:8000 cle-de-test
        python Deployment/tester_api.py https://<domaine> <ta-cle>

La clé peut aussi être donnée par la variable d'environnement API_KEY.
N'utilise que la bibliothèque standard de Python : aucune installation nécessaire.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

# Adresse de l'API : 1er argument de la ligne de commande, sinon l'API locale.
# rstrip("/") évite un double "/" dans "http://.../score".
URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
# Clé API : 2e argument, sinon variable d'environnement API_KEY
CLE = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("API_KEY", "")

# Messages de test : sains, ambigus, toxiques, plus un cas invalide
EXEMPLES = [
    # Sains : score attendu proche de 0
    "gg wp team",
    "nice shot, well played",
    # Ambigus : c'est sur eux qu'on attend des scores intermédiaires (ni 0 ni 100)
    "gg ez",                            # victoire... avec une pointe de moquerie
    "noob",                             # insulte légère, souvent dite pour rire
    "you're mad lol",                   # taquinerie
    "wtf was that",                     # agacement, sans viser personne
    "ty for nothing",                   # ironie
    "cyka blyat",                       # juron en russe (langue étrangère)
    # Toxiques : score attendu proche de 100
    "useless noob",                     # insulte
    "you are so stupid, uninstall",     # insulte
    "kys idiot",                        # incitation au suicide (très grave)
    # Invalide : texte vide -> erreur 422 attendue (validation d'entrée)
    "",
]


def envoyer(texte, cle=CLE):
    """
    Envoie UN texte à la route POST /score, avec la clé API dans l'en-tête X-API-Key.
    Retourne (code HTTP, corps de la réponse en JSON, temps de réponse en ms).
    """
    entetes = {"Content-Type": "application/json"}
    if cle:
        entetes["X-API-Key"] = cle
    # Requête HTTP POST avec un corps JSON : {"texte": "..."}
    requete = urllib.request.Request(
        f"{URL}/score",
        data=json.dumps({"texte": texte}).encode(),
        headers=entetes,
        method="POST",
    )
    debut = time.perf_counter()
    try:
        with urllib.request.urlopen(requete) as r:
            code, corps = r.status, json.loads(r.read())       # succès (200)
    except urllib.error.HTTPError as e:
        # Erreur renvoyée par l'API (ex : 422 si le texte est invalide) :
        # on l'affiche au lieu de planter, c'est un résultat de test attendu
        code, corps = e.code, json.loads(e.read())
    return code, corps, (time.perf_counter() - debut) * 1000


def afficher(libelle, code, corps, ms):
    """Affichage : message envoyé, code HTTP, temps de réponse, puis la réponse."""
    print(f"{libelle:35} -> HTTP {code}  ({ms:.0f} ms)")
    print(f"    {json.dumps(corps, ensure_ascii=False)}")


if __name__ == "__main__":
    print(f"API testée : {URL}\n")

    # Vérification préalable : l'API est-elle joignable ? (route /health, sans clé)
    try:
        urllib.request.urlopen(f"{URL}/health", timeout=10)
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"ERREUR : impossible de joindre l'API ({e}).\n"
                 f"Vérifier qu'elle est lancée (en local : 'Uvicorn running on ...').")

    # Tests de sécurité (étape 4) : sans clé et avec une mauvaise clé -> 401 attendu
    print("--- Sécurité : requêtes refusées attendues (HTTP 401) ---")
    afficher("[sans clé] 'gg wp'", *envoyer("gg wp", cle=""))
    afficher("[mauvaise clé] 'gg wp'", *envoyer("gg wp", cle="mauvaise-cle"))

    # Exemples de requêtes avec la bonne clé
    print("\n--- Exemples de requêtes (avec la clé) ---")
    if not CLE:
        print("ATTENTION : aucune clé fournie, les requêtes seront refusées (401).")
    for texte in EXEMPLES:
        afficher(repr(texte), *envoyer(texte))
