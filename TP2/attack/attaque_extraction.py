"""
TP2 - Étape 2 : attaque par extraction de modèle (model stealing)
==================================================================


Principe : on se met dans la peau d'un attaquant qui n'a QUE l'accès à l'API.
  1. On envoie des messages à l'API et on récupère ses réponses (label toxique / non toxique)
  2. Avec ces réponses, on entraîne notre propre modèle "copie" (TF-IDF + régression logistique)
  3. On regarde à quel point la copie ressemble à Laya, en fonction du nombre de requêtes envoyées
  4. On mesure aussi la latence de l'API avant et pendant l'attaque


Lancement (depuis la racine du dépôt, après avoir défini l'URL et la clé) :
    $env:API_URL="http://X.X.X.X/score" ; $env:API_KEY="la-cle-du-binome"
    python TP2/attack/attaque_extraction.py
Résultats  :  TP2/resultats/  (metrics.csv, metrics.json, graphiques .png)

Étape 3 (mesure APRÈS la défense) : donner une étiquette au lancement.
    $env:ETIQUETTE="apres_defense" ; python TP2/attack/attaque_extraction.py
-> fichiers metrics_apres_defense.csv, .json, .png et un cache SÉPARÉ, vide au
   départ : l'attaque interroge vraiment l'API protégée (sinon les réponses
   déjà en cache feraient croire que la défense ne sert à rien).
"""


import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score


# ---------------------------------------------------------------------------
# CONFIG -> API de la cible (le binôme)
# ---------------------------------------------------------------------------
# URL et clé passées par variables d'environnement, JAMAIS écrites en dur ici
# (sinon la clé du binôme se retrouverait sur git).
#   PowerShell :  $env:API_URL="http://X.X.X.X/score" ; $env:API_KEY="la-cle"
#   bash       :  export API_URL=http://X.X.X.X/score  API_KEY=la-cle
API_URL = os.getenv("API_URL", "http://localhost:8000/score")
API_KEY = os.getenv("API_KEY", "")
HEADERS = {"X-API-Key": API_KEY}


# Chemins calculés à partir de ce fichier : marche quel que soit le dossier courant.
RACINE = Path(__file__).resolve().parents[2]


# Messages que l'attaquant envoie. Il n'a PAS les données d'entraînement de la
# cible ; on prend le jeu public GameTox (colonne "message", on ignore le label).
ATTACKER_CSV = RACINE / "TP1" / "data_train" / "train_clean.csv"


# Jeu de test avec les vrais labels (colonnes "message" et "label", >= 1 = toxique)
# -> sert uniquement à NOUS pour mesurer la copie, l'attaquant ne l'a pas.
TEST_CSV = RACINE / "TP1" / "data_eval" / "val_clean.csv"
COL_TEXTE = "message"           # nom de la colonne texte dans ces CSV


# Nombre de requêtes "volées" qu'on teste : on regarde comment la copie
# s'améliore quand l'attaquant envoie de plus en plus de requêtes
BUDGETS = [100, 250, 500, 1000, 2000]


N_WORKERS = 8          # requêtes envoyées en parallèle pendant l'attaque
N_BASELINE = 30        # requêtes "normales" pour mesurer la latence de base
TIMEOUT = 30           # secondes
MAX_RETRIES = 5        # si l'API nous limite (429/503), on réessaie X fois


RESULTS_DIR = str(RACINE / "TP2" / "resultats")

# Étiquette du lancement ("" = attaque initiale, "apres_defense" = étape 3...).
# Chaque étiquette a ses propres fichiers de résultats ET son propre cache.
ETIQUETTE = os.getenv("ETIQUETTE", "").strip()
SUFFIXE = f"_{ETIQUETTE}" if ETIQUETTE else ""
CACHE_FILE = os.path.join(RESULTS_DIR, f"cache_reponses_api{SUFFIXE}.json")


def fichier_resultat(nom, ext):
    """metrics + .csv -> TP2/resultats/metrics_<etiquette>.csv"""
    return os.path.join(RESULTS_DIR, f"{nom}{SUFFIXE}.{ext}")




def build_payload(text):
    """Format attendu par l'API (TP1/Deployment/api.py) : {"texte": "..."}."""
    return {"texte": text[:1000]}           # l'API refuse (422) au-delà de 1000 caractères




def parse_response(data):
    """Transforme la réponse JSON de l'API en 0 / 1 (1 = toxique).
    L'API cible renvoie son propre booléen "toxique" (calculé à partir de ses
    seuils par catégorie) : on vole directement CETTE décision pour que le clone
    reproduise fidèlement la frontière du modèle. Repli sur le score si absent."""
    if "toxique" in data:
        return int(bool(data["toxique"]))
    return int(data.get("score", 0) >= 50)




# ---------------------------------------------------------------------------
# Appels à l'API
# ---------------------------------------------------------------------------
def query_api(text):
    """Envoie un message à l'API, renvoie (label, latence en ms).


    Si l'API nous limite (429 Too Many Requests, ou 503), on ne plante pas :
    on attend de plus en plus longtemps puis on réessaie (backoff exponentiel).
    C'est ce que fait un vrai attaquant face à une limite de débit : à l'étape 3,
    on vérifie si la défense tient malgré ce comportement « patient »."""
    for essai in range(MAX_RETRIES):
        start = time.perf_counter()
        r = requests.post(API_URL, json=build_payload(text), headers=HEADERS, timeout=TIMEOUT)
        latency_ms = (time.perf_counter() - start) * 1000
        if r.status_code in (429, 503):
            # attente qui double à chaque essai (1s, 2s, 4s...) + un peu d'aléa
            attente = (2 ** essai) + random.random()
            # si l'API indique quand réessayer (en-tête Retry-After), on l'écoute
            attente = float(r.headers.get("Retry-After", attente))
            time.sleep(attente)
            continue
        r.raise_for_status()
        return parse_response(r.json()), latency_ms
    raise RuntimeError("Trop d'erreurs 429/503 : l'API nous limite vraiment")




def query_many(texts, n_workers, cache):
    """Interroge l'API sur une liste de messages, en parallèle.
    On garde les réponses en cache pour ne pas re-surcharger l'API
    (Laya est lent) si on relance le script."""
    todo = [t for t in texts if t not in cache]
    latencies = []
    echecs = 0


    def worker(text):
        try:
            label, lat = query_api(text)
            return text, label, lat
        # RuntimeError = requête toujours bloquée (429/503) après tous les essais :
        # avec une défense par limite de débit, c'est normal, on ne plante pas.
        except (requests.RequestException, RuntimeError) as e:
            print(f"  erreur API : {e}")
            return text, None, None


    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        for i, (text, label, lat) in enumerate(pool.map(worker, todo), 1):
            if label is not None:
                cache[text] = label
                latencies.append(lat)
            else:
                echecs += 1
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} requêtes envoyées")


    labels = [cache.get(t) for t in texts]
    return labels, latencies, echecs




# ---------------------------------------------------------------------------
# Métriques
# ---------------------------------------------------------------------------
def metrics(y_true, y_pred):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "taux_faux_positifs": float(fp / (fp + tn)) if (fp + tn) else 0.0,
    }




def main():
    if not API_KEY:
        sys.exit("Définir API_KEY (la clé de l'API cible) avant de lancer l'attaque.")
    print(f"Cible : {API_URL}" + (f"   (étiquette : {ETIQUETTE})" if ETIQUETTE else ""))
    try:
        base = API_URL.rsplit("/", 1)[0]     # .../score -> ...
        requests.get(f"{base}/health", timeout=10).raise_for_status()
    except requests.RequestException:
        sys.exit(f"L'API ne répond pas ({API_URL}) : vérifier l'URL et qu'elle est en ligne.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    cache = json.load(open(CACHE_FILE, encoding="utf-8")) if os.path.exists(CACHE_FILE) else {}


    attacker_texts = pd.read_csv(ATTACKER_CSV, keep_default_na=False)[COL_TEXTE].astype(str)
    attacker_texts = [t for t in attacker_texts if t.strip()]
    test = pd.read_csv(TEST_CSV, keep_default_na=False)
    test = test[test[COL_TEXTE].astype(str).str.strip() != ""]
    test_texts = test[COL_TEXTE].astype(str).tolist()
    y_true = (test["label"].astype(int) >= 1).to_numpy().astype(int)   # toxique = note >= 1


    budget_max = min(max(BUDGETS), len(attacker_texts))
    budgets = [b for b in BUDGETS if b <= budget_max]


    # 1) Latence de base : quelques requêtes une par une, API "au calme"
    print(f"[1/4] Latence de base ({N_BASELINE} requêtes séquentielles)")
    baseline_lat = []
    for t in test_texts[:N_BASELINE]:
        try:
            baseline_lat.append(query_api(t)[1])
        except (requests.RequestException, RuntimeError) as e:
            print(f"  erreur API : {e}")
    if not baseline_lat:
        sys.exit("Aucune requête n'a abouti : vérifier la clé API et le format de la requête.")


    # 2) Réponses de Laya sur le jeu de test (référence pour comparer la copie)
    print("[2/4] Prédictions de Laya sur le jeu de test")
    y_laya, _, _ = query_many(test_texts, N_WORKERS, cache)
    y_laya = np.array([-1 if y is None else y for y in y_laya])
    ok = y_laya != -1   # on ignore les messages où l'API n'a pas répondu
    if not ok.any():
        sys.exit("L'API n'a répondu à aucun message du jeu de test.")
    laya = metrics(y_true[ok], y_laya[ok])


    # 3) L'attaque : on vole les labels de l'API
    print(f"[3/4] Attaque : {budget_max} requêtes avec {N_WORKERS} threads")
    stolen, attack_lat, echecs = query_many(attacker_texts[:budget_max], N_WORKERS, cache)
    json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  {echecs} requêtes de l'attaque bloquées ou en erreur")


    # 4) On entraîne une copie pour chaque budget et on la compare à Laya
    print("[4/4] Entraînement des copies")
    rows = []
    for b in budgets:
        X = [t for t, y in zip(attacker_texts[:b], stolen[:b]) if y is not None]
        y = [y for y in stolen[:b] if y is not None]
        if len(set(y)) < 2:
            print(f"  budget {b} : une seule classe renvoyée, copie impossible")
            continue


        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        copie = LogisticRegression(max_iter=1000, class_weight="balanced")
        copie.fit(vec.fit_transform(X), y)


        y_copie = copie.predict(vec.transform(test_texts))
        m = metrics(y_true[ok], y_copie[ok])
        m["accord_avec_laya"] = float(np.mean(y_copie[ok] == y_laya[ok]))
        m["nb_requetes"] = b
        rows.append(m)
        print(f"  {b:>5} requêtes -> accord {m['accord_avec_laya']:.1%}, "
              f"accuracy {m['accuracy']:.1%}, FPR {m['taux_faux_positifs']:.1%}")


    df = pd.DataFrame(rows)
    df.to_csv(fichier_resultat("metrics", "csv"), index=False)


    latence = {
        "base_moyenne_ms": float(np.mean(baseline_lat)),
        "base_p95_ms": float(np.percentile(baseline_lat, 95)),
        "attaque_moyenne_ms": float(np.mean(attack_lat)) if attack_lat else None,
        "attaque_p95_ms": float(np.percentile(attack_lat, 95)) if attack_lat else None,
    }
    # Requêtes de l'attaque qui n'ont rien rapporté (bloquées par la défense...)
    attaque = {"requetes_envoyees": budget_max, "requetes_bloquees": echecs,
               "taux_blocage": echecs / budget_max if budget_max else 0.0}
    json.dump({"etiquette": ETIQUETTE or "attaque_initiale", "laya": laya, "copies": rows,
               "latence": latence, "attaque": attaque},
              open(fichier_resultat("metrics", "json"), "w"), indent=2)


    # ---------------- Graphiques ----------------
    if df.empty:
        print("Aucune copie n'a pu être entraînée (trop peu de réponses) : pas de graphique.")
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(df["nb_requetes"], df["accord_avec_laya"], "o-", label="Accord copie / Laya")
    ax.plot(df["nb_requetes"], df["accuracy"], "s-", label="Accuracy de la copie")
    ax.plot(df["nb_requetes"], df["taux_faux_positifs"], "^-", label="Faux positifs de la copie")
    ax.axhline(laya["accuracy"], ls="--", c="grey", label="Accuracy de Laya (référence)")
    ax.axhline(laya["taux_faux_positifs"], ls=":", c="grey", label="Faux positifs de Laya")
    ax.set_xscale("log")
    ax.set_xlabel("Nombre de requêtes envoyées à l'API")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.05)
    ax.set_title("Extraction de modèle : qualité de la copie selon le nombre de requêtes")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fichier_resultat("extraction_metrics", "png"), dpi=150)


    if attack_lat:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.boxplot([baseline_lat, attack_lat], showfliers=False)
        ax.set_xticks([1, 2], ["Normal (1 à la fois)", f"Pendant l'attaque ({N_WORKERS} threads)"])
        ax.set_ylabel("Latence (ms)")
        ax.set_title("Latence de l'API")
        ax.grid(alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(fichier_resultat("latence", "png"), dpi=150)


    print("\nLaya (référence) :", {k: round(v, 3) for k, v in laya.items()})
    print("Latence :", {k: round(v, 1) for k, v in latence.items() if v is not None})
    print(f"Résultats dans {RESULTS_DIR}/")




if __name__ == "__main__":
    main()


 
