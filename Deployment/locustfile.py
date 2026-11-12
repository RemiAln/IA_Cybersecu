import os
import random

from locust import HttpUser, LoadTestShape, between, events, task

# Étape 5 - montée en charge de l'API (Locust).
# Scénario choisi avec SCENARIO=montee|stress|panne, clé API avec API_KEY.
API_KEY = os.environ.get("API_KEY", "")
SCENARIO = os.environ.get("SCENARIO", "montee")

# Messages de chat inventés (aucune donnée du dataset), classés par catégorie
# attendue : Locust mesure ainsi la latence de chaque catégorie séparément.
CORPUS = {
    "sain": ["gg wp team", "nice shot, well played", "thanks for the heal",
             "go mid", "anyone want to group up", "push the left flank"],
    "ambigu": ["gg ez", "noob", "you're mad lol", "wtf was that",
               "ty for nothing", "learn to play"],
    "toxique": ["useless noob", "you are so stupid, uninstall",
                "worst team ever", "kys idiot"],
}

# Paliers : (secondes écoulées à la fin du palier, joueurs connectés, joueurs ajoutés par seconde)
SCENARIOS = {
    "montee": [(120, 5, 1), (240, 10, 1), (360, 20, 2), (480, 40, 4), (600, 60, 5)],  # croissance progressive
    "stress": [(60, 5, 5), (360, 100, 50)],                                          # pic brutal à 100
    "panne": [(300, 20, 5)],                     # charge constante, supprimer un pod pendant le test
}


class JoueurVirtuel(HttpUser):
    """Un joueur qui écrit un message toutes les 1 à 3 secondes."""

    wait_time = between(1, 3)

    def on_start(self):
        # Avant de jouer : l'API répond-elle ? (route /health, sans clé)
        self.client.get("/health", name="/health (démarrage)")

    @task
    def ecrire_message(self):
        categorie = random.choice(list(CORPUS))
        texte = random.choice(CORPUS[categorie])
        with self.client.post("/score", json={"texte": texte},
                              headers={"X-API-Key": API_KEY},
                              name=f"/score [{categorie}]",   # statistiques par catégorie
                              catch_response=True) as rep:
            # Tout code autre que 200 compte comme une erreur
            if rep.status_code != 200:
                rep.failure(f"HTTP {rep.status_code}")


class ProfilDeCharge(LoadTestShape):
    """Nombre de joueurs connectés au cours du temps, selon le scénario."""

    def tick(self):
        ecoule = self.get_run_time()
        palier = next((p for p in SCENARIOS[SCENARIO] if ecoule < p[0]), None)
        if palier is None:
            return None                  # tous les paliers sont passés : fin du test
        _, joueurs, cadence = palier
        return joueurs, cadence


@events.test_stop.add_listener
def resume_final(environment, **_):
    """Indicateurs demandés par l'énoncé : latence moyenne, P95, P99, taux d'erreur."""
    total = environment.stats.total
    if total.num_requests == 0:
        print("\nAucune requête envoyée.")
        return
    taux_erreur = 100 * total.num_failures / total.num_requests
    print(f"\n===== Résumé du scénario '{SCENARIO}' =====")
    print(f"Requêtes envoyées : {total.num_requests}")
    print(f"Débit moyen       : {total.total_rps:.1f} requêtes/s")
    print(f"Latence moyenne   : {total.avg_response_time:.0f} ms")
    print(f"Latence P95 / P99 : {total.get_response_time_percentile(0.95):.0f} ms"
          f" / {total.get_response_time_percentile(0.99):.0f} ms")
    print(f"Taux d'erreur     : {taux_erreur:.2f} %")
