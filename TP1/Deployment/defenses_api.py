"""
TP2 - Étape 3 : DÉFENSES contre l'extraction de modèle (model stealing)
=======================================================================

L'attaquant vole notre modèle en envoyant des milliers de requêtes et en
récupérant les réponses. Le cours (partie « Sécurité du modèle ») recommande
plusieurs contre-mesures ; on en implémente deux ici :

  1. LIMITER le nombre de requêtes par client (rate limiting)
     -> l'attaquant ne peut plus envoyer des milliers de requêtes d'affilée.

  2. APPAUVRIR la réponse : ne renvoyer que le verdict (toxique / non toxique)
     et un score arrondi, sans le score exact ni les seuils.
     -> l'attaquant apprend moins vite, et surtout il perd le signal fin
        qui l'aidait à régler son attaque. Bonus : ça gêne AUSSI l'évasion,
        qui se servait du score pour ajuster l'obfuscation.

Ces deux défenses s'ajoutent à l'API FastAPI existante, sans toucher au modèle.
Aucune dépendance à installer : tout est en mémoire.

Limite connue : le compteur est dans la mémoire de CHAQUE pod. Avec N pods
derrière le load balancer, un client peut obtenir jusqu'à N x 60 requêtes par
minute. Une limite globale exacte demanderait Cloud Armor (WAF) devant l'API.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


# ===========================================================================
# DÉFENSE 1 : limitation du nombre de requêtes (rate limiting)
# ===========================================================================
class LimiteurDebit:
    """Limiteur "fenêtre glissante" en mémoire.

    On garde l'horodatage des requêtes récentes de chaque client. À chaque
    appel, on jette celles qui datent de plus de `fenetre` secondes, et si
    le client dépasse `max_requetes` sur la fenêtre, on refuse.

    Le client est identifié par sa clé API si elle existe, sinon par son IP.
    """

    def __init__(self, max_requetes=60, fenetre=60):
        self.max_requetes = max_requetes      # ex : 60 requêtes...
        self.fenetre = fenetre                # ...par 60 secondes
        self._historique = defaultdict(deque)  # client -> horodatages
        self._verrou = threading.Lock()

    def _identifier(self, request):
        cle = request.headers.get("X-API-Key")
        if cle:
            return f"cle:{cle}"
        client = request.client
        return f"ip:{client.host if client else 'inconnu'}"

    def verifier(self, request):
        """Lève une erreur 429 si le client a dépassé sa limite."""
        client = self._identifier(request)
        maintenant = time.time()
        with self._verrou:
            q = self._historique[client]
            # on enlève les requêtes trop vieilles (hors de la fenêtre)
            while q and maintenant - q[0] > self.fenetre:
                q.popleft()
            if len(q) >= self.max_requetes:
                # trop de requêtes : on calcule dans combien de temps ça se libère
                attente = int(self.fenetre - (maintenant - q[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Trop de requêtes, réessayez plus tard.",
                    headers={"Retry-After": str(attente)},
                )
            q.append(maintenant)


# instance partagée par toute l'API
limiteur = LimiteurDebit(max_requetes=60, fenetre=60)


def verifier_debit(request: Request):
    """Dépendance FastAPI : ajoutée sur la route de prédiction.
    Refuse la requête (429) si le client dépasse la limite."""
    limiteur.verifier(request)


# ===========================================================================
# DÉFENSE 2 : réponse appauvrie (label seul, sans le score exact)
# ===========================================================================
def reponse_sure(score, seuil=50.0, mode="label"):
    """Transforme la sortie brute du modèle en réponse à renvoyer au client.

    mode="label"  -> on ne renvoie QUE le verdict (le plus protecteur).
    mode="arrondi"-> on renvoie un score arrondi (ex : 0, 25, 50, 75, 100),
                     utile si l'appli a vraiment besoin d'une idée du score.

    Dans les deux cas, on ne renvoie JAMAIS le seuil ni le score exact, qui
    aidaient l'attaquant.
    """
    toxique = score >= seuil
    if mode == "arrondi":
        score_grossier = round(score / 25) * 25     # on garde 5 niveaux seulement
        return {"toxique": toxique, "niveau": score_grossier}
    return {"toxique": toxique}                      # label seul
