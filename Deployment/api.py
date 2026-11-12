"""
TP1 - Étapes 3 et 4 : API "Digital Social Score"

Reçoit un texte et renvoie un score de toxicité de 0 à 100, calculé par le
modèle Laya entraîné à l'étape 2 (dossier modeles/laya).

Sécurité (étape 4) :
  - clé API obligatoire sur /score (en-tête X-API-Key), sinon erreur 401
  - validation des entrées (texte de 1 à 1 000 caractères), sinon erreur 422
  - logs pseudonymisés : le texte reçu n'est JAMAIS écrit dans les journaux,
    l'IP du client est remplacée par une empreinte (HMAC)

Supervision (étape 6) :
  - métriques Prometheus (requêtes, codes HTTP, latence, temps d'inférence, scores)
    servies sur un PORT SÉPARÉ (9090), que le Service n'expose pas sur Internet :
    seul Prometheus, à l'intérieur du cluster, peut les lire

Variables d'environnement (fournies par un Secret Kubernetes, jamais dans le code) :
  API_KEY   clé(s) API acceptée(s), séparées par des virgules
  LOG_SALT  clé secrète utilisée pour pseudonymiser les IP dans les logs

Lancement local (depuis la racine du projet, PowerShell) :
  $env:API_KEY="cle-de-test"; $env:LOG_SALT="sel-de-test"; uvicorn Deployment.api:app
Documentation : http://127.0.0.1:8000/docs  (bouton "Authorize" pour saisir la clé)
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time

# Avant d'importer laya : pas de TensorFlow (blocage connu), et aucun accès à
# Internet pour le modèle (il est déjà dans l'image, rien à télécharger).
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import laya
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import APIKeyHeader
from prometheus_client import Histogram, start_http_server
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from data_transformation.nettoyage import nettoyer

DOSSIER_MODELE = "modeles/laya"   # relatif à la racine du projet (ou /app dans le conteneur)
LONGUEUR_MAX = 128                # identique à l'entraînement (modele_laya.py)
SEUIL_TOXIQUE = 0.5               # identique à l'évaluation : P(note >= 1) >= 0.5
NB_NOTES = 6                      # notes 0 à 5
PORT_METRIQUES = 9090             # port interne des métriques Prometheus (étape 6)

# ---------------------------------------------------------------------------
# Métriques Prometheus propres au modèle (étape 6)
# (les métriques HTTP - requêtes, codes, latence - sont ajoutées plus bas
#  automatiquement par prometheus_fastapi_instrumentator)
# ---------------------------------------------------------------------------
# Temps de calcul du modèle seul. Comparé à la latence HTTP totale, il montre
# combien de temps les requêtes passent à ATTENDRE (file d'attente sous la charge).
LATENCE_INFERENCE = Histogram(
    "inference_latency_seconds", "Latence d'inférence du modèle Laya",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
)
# Répartition des scores renvoyés : une hausse soudaine des scores élevés peut
# signaler un comportement anormal (raid de messages toxiques, spam...).
SCORES = Histogram(
    "dss_score_toxicite", "Scores de toxicité renvoyés (0 à 100)",
    buckets=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
)

# ---------------------------------------------------------------------------
# Secrets (étape 4) : lus dans l'environnement, jamais écrits dans le code
# ---------------------------------------------------------------------------
# Plusieurs clés possibles (une par client), séparées par des virgules
CLES_API = [c.strip() for c in os.environ.get("API_KEY", "").split(",") if c.strip()]
# Sel des empreintes d'IP : sans lui, on pourrait retrouver une IP en testant
# toutes les adresses possibles. S'il manque, on en tire un au hasard.
SEL_LOGS = os.environ.get("LOG_SALT", "").encode() or secrets.token_bytes(32)

# ---------------------------------------------------------------------------
# Logs : une ligne JSON par requête sur la sortie standard. Sur GKE, Cloud
# Logging les récupère automatiquement et sait filtrer sur chaque champ.
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
journal = logging.getLogger("dss")


def pseudonymiser(valeur: str) -> str:
    """Empreinte HMAC-SHA256 (8 caractères) : même entrée -> même empreinte,
    mais impossible de retrouver la valeur d'origine sans le sel secret."""
    return hmac.new(SEL_LOGS, valeur.encode(), hashlib.sha256).hexdigest()[:8]


def log(**champs):
    journal.info(json.dumps(champs, ensure_ascii=False))


if not CLES_API:
    # Fail-closed : sans clé configurée, /score refusera TOUTES les requêtes
    log(niveau="ATTENTION", message="API_KEY non définie : /score refusera toutes les requêtes")

# ---------------------------------------------------------------------------
# Chargement du modèle : UNE SEULE FOIS, au démarrage de l'API
# (~650 Mo : le recharger à chaque requête prendrait trop de temps)
# ---------------------------------------------------------------------------
agent = laya.load(DOSSIER_MODELE, device="cpu")

# La question posée au modèle est relue dans le modèle lui-même (questions.json) :
# on est certain de poser EXACTEMENT la question apprise à l'entraînement.
with open(os.path.join(DOSSIER_MODELE, "questions.json"), encoding="utf-8") as f:
    QUESTIONS = json.load(f)
ID_QUESTION = next(iter(QUESTIONS))          # "toxicite"


def predire(texte: str) -> np.ndarray:
    """Probabilités des 6 notes (0 à 5) pour un texte déjà nettoyé."""
    with LATENCE_INFERENCE.time():           # mesure le temps de calcul du modèle
        reponse = agent.predict_batch([texte], QUESTIONS, max_len=LONGUEUR_MAX)[0]
    probas = reponse["answers"][ID_QUESTION]["probabilities"]
    return np.array([probas[str(k)] for k in range(NB_NOTES)])


# Échauffement : le premier calcul est toujours plus lent ; on le fait ici,
# avant que l'API n'accepte des requêtes.
predire("gg")

app = FastAPI(
    title="Digital Social Score",
    description="Détection de toxicité : renvoie un score de 0 (sain) à 100 (très toxique). "
                "La route /score exige une clé API (en-tête X-API-Key).",
    version="2.1",
)

# Métriques HTTP automatiques : nombre de requêtes et latence par route et par code.
# - should_group_status_codes=False : garde 401 et 422 séparés (au lieu de "4xx"),
#   pour repérer une attaque par fausses clés (pic de 401)
# - /health exclu : les sondes Kubernetes fausseraient les statistiques
# Pas de .expose(app) comme dans le cours : /metrics serait alors public sur l'IP
# du load balancer. Les métriques sont servies sur le port interne 9090.
Instrumentator(should_group_status_codes=False,
               excluded_handlers=["/health"]).instrument(app)
start_http_server(PORT_METRIQUES)


# ---------------------------------------------------------------------------
# Authentification par clé API (étape 4)
# ---------------------------------------------------------------------------
# auto_error=False : on gère nous-mêmes l'erreur, pour renvoyer un 401 explicite
schema_cle = APIKeyHeader(name="X-API-Key", auto_error=False)


def verifier_cle(request: Request, cle: str = Depends(schema_cle)):
    """Refuse la requête (401) si la clé est absente ou inconnue."""
    # compare_digest : comparaison en temps constant, pour qu'un attaquant ne
    # puisse pas deviner la clé caractère par caractère en mesurant le temps
    if not cle or not any(secrets.compare_digest(cle, c) for c in CLES_API):
        raise HTTPException(status_code=401, detail="Clé API absente ou invalide")
    # Identifiant pseudonymisé du client (empreinte de sa clé), pour les logs
    request.state.client_cle = pseudonymiser(cle)


# ---------------------------------------------------------------------------
# Journalisation de chaque requête (middleware : s'exécute autour de TOUTES
# les routes, y compris quand la requête est refusée en 401 ou 422)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def journaliser(request: Request, call_next):
    debut = time.perf_counter()
    reponse = await call_next(request)
    if request.url.path != "/health":       # les sondes Kubernetes ne sont pas journalisées
        # Derrière le load balancer, la vraie IP du client est dans X-Forwarded-For
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() \
            or (request.client.host if request.client else "inconnue")
        log(
            route=request.url.path,
            methode=request.method,
            statut=reponse.status_code,
            duree_ms=round((time.perf_counter() - debut) * 1000, 1),
            client_ip=pseudonymiser(ip),                            # IP pseudonymisée
            client_cle=getattr(request.state, "client_cle", None),  # clé pseudonymisée
            score=getattr(request.state, "score", None),
            longueur_texte=getattr(request.state, "longueur", None),
            # Le TEXTE n'est volontairement jamais journalisé (RGPD : minimisation)
        )
    return reponse


# ---------------------------------------------------------------------------
# Format des requêtes et des réponses (validé automatiquement par FastAPI)
# ---------------------------------------------------------------------------
class Requete(BaseModel):
    # Validation d'entrée : texte obligatoire, entre 1 et 1 000 caractères
    texte: str = Field(..., min_length=1, max_length=1000, examples=["gg wp team"])


class Reponse(BaseModel):
    score: float           # 0 à 100 = probabilité que le message soit toxique, en %
    note: int              # gravité la plus probable, de 0 (sain) à 5
    toxique: bool          # True si score >= 50


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Vérifie que l'API répond (utilisé par Kubernetes). Pas de clé requise."""
    return {"statut": "ok"}


@app.post("/score", response_model=Reponse, dependencies=[Depends(verifier_cle)])
def score(requete: Requete, request: Request):
    # 1. Même nettoyage qu'à l'entraînement (minuscules, ponctuation...)
    texte = nettoyer(requete.texte)

    # 2. Prédiction : probabilités des 6 notes (0 à 5)
    probas = predire(texte)

    # 3. Score 0-100 = probabilité que le message soit toxique (note >= 1), en %.
    #    Même principe que l'API Perspective de Google. La gravité est donnée à
    #    part dans "note" : le modèle est fiable pour dire "toxique ou non", moins
    #    pour la gravité exacte (trop peu d'exemples de notes 4 et 5).
    p_toxique = float(1 - probas[0])
    score_0_100 = round(p_toxique * 100, 1)

    # Informations transmises au journal (le score et la LONGUEUR, pas le texte)
    request.state.score = score_0_100
    request.state.longueur = len(requete.texte)
    SCORES.observe(score_0_100)              # métrique Prometheus (étape 6)

    return Reponse(
        score=score_0_100,
        note=int(probas.argmax()),
        toxique=p_toxique >= SEUIL_TOXIQUE,
    )
