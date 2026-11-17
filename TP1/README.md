# Digital Social Score – IA & cybersécurité (TP ESIGELEC)

API qui détecte la toxicité d'un message de chat (insultes, racisme, harcèlement, propos
haineux) et lui attribue un **score de 0 à 100**. Le projet couvre toute la chaîne :
anonymisation des données, entraînement et comparaison de trois modèles, déploiement
sécurisé sur Google Kubernetes Engine, et tests de montée en charge.

```
 Données GameTox ──► anonymisation ──► nettoyage ──► 3 modèles (LSTM, BERT-Mini, Laya)
                     (RGPD)                              │ meilleur compromis : Laya
                                                         ▼
 Client ──HTTP + clé API──► Load Balancer GKE ──► pods API (FastAPI + Laya) ──► score 0-100
                                                   │  2 à 10 pods (autoscaling)
                                                   └► journaux pseudonymisés (Cloud Logging)
```

- **Documentation de l'API et exemples de requêtes** : [`docs/API.md`](docs/API.md)
- **Registre des traitements RGPD** : [`REGISTRE_RGPD.md`](REGISTRE_RGPD.md)

---

## Organisation du dépôt

```
TP1/
├── data_train/                  jeu d'entraînement
│   ├── train_raw.csv            messages bruts GameTox (42 959 lignes)
│   ├── train_anon.csv           anonymisé (généré, étape 1)
│   └── train_clean.csv          anonymisé + nettoyé (généré, étape 2)
├── data_eval/                   jeu d'évaluation (5 367 lignes, mêmes 3 versions)
├── data_transformation/
│   ├── anonymisation.py         étape 1 : produit les *_anon.csv
│   ├── nettoyage.py             étape 2 : produit les *_clean.csv
│   └── evaluation.py            étape 2 : code commun aux modèles (données, métriques)
├── model/
│   ├── modele_lstm.py           étape 2 : modèle statistique (LSTM)
│   ├── modele_bert.py           étape 2 : modèle transformer (BERT-Mini)
│   ├── modele_laya.py           étape 2 : modèle de décision (Laya)
│   └── comparer_modeles.py      étape 2 : tableau comparatif des modèles
├── Deployment/
│   ├── api.py                   étapes 3-4 : API FastAPI (score, clé API, logs pseudonymisés)
│   ├── Dockerfile               étape 3 : image de l'API
│   ├── cloudbuild.yaml          étape 3 : construction de l'image sur Google Cloud Build
│   ├── tester_api.py            étapes 3-4 : exemples de requêtes et tests de sécurité
│   ├── locustfile.py            étape 5 : scénarios de charge (montée, stress, panne)
│   ├── tester_attaques.py       étape 6 : simulation d'attaques (injection, contournement, fausses clés)
│   ├── k8s/                     étapes 3 et 6 : manifestes Kubernetes
│   │   ├── deployment.yaml      pods de l'API (2 copies, ressources, sondes de santé, secrets)
│   │   ├── service.yaml         répartiteur de charge (IP publique)
│   │   ├── hpa.yaml             autoscaling de 2 à 10 pods selon le CPU
│   │   └── podmonitoring.yaml   collecte des métriques par Managed Prometheus
│   └── supervision/
│       └── grafana.yaml         étape 6 : Grafana (tableaux de bord, accès privé)
├── docs/
│   └── API.md                   documentation de l'API + exemples de requêtes / réponses
├── resultats/                   métriques des modèles (JSON) et rapports de charge
├── modeles/                     modèles entraînés (NON versionné : trop lourd)
├── requirements.txt             dépendances des étapes 1, 2 et 5
├── requirements-api.txt         dépendances de l'API (image Docker)
├── REGISTRE_RGPD.md             registre des traitements
└── TP1_Digital_Social_Score.pdf énoncé
```

**Toutes les commandes se lancent depuis le dossier `TP1/`**, avec `python -m dossier.script`
(sinon les imports entre dossiers et les chemins des données ne fonctionnent pas).

### Ce qui n'est pas dans le dépôt (volontairement)
| Élément | Pourquoi | Où il se trouve |
|---|---|---|
| `modeles/` | trop lourd (Laya : ~650 Mo) ; se régénère avec les scripts de `model/` | sur les postes du binôme |
| `.env` | contient la clé de pseudonymisation des pseudos (étape 1) | sur les postes du binôme |
| Clé API, sel des journaux | secrets de production | Secret Kubernetes `dss-secrets` dans le cluster |

---

## Installation

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows (PowerShell)  |  source .venv/bin/activate (Linux/macOS)
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

---

## Étape 1 : anonymisation des données

```bash
# Clé de pseudonymisation des pseudos : dans le fichier .env (non versionné)
#   PSEUDO_KEY=une_longue_chaine_aleatoire
python -m data_transformation.anonymisation
```

Traitement de chaque message :
```
message brut
   ├─ e-mail, URL, IP, téléphone (regex, phonenumbers) → <EMAIL> <URL> <IP> <PHONE>
   ├─ pseudos de joueurs (HMAC + clé secrète)          → <USER_xxxxxxxx>
   └─ prénoms (NER spaCy + dictionnaire de prénoms)    → <PERSON>
message anonymisé
```
Sans `PSEUDO_KEY`, une clé aléatoire est tirée : les codes `<USER_...>` changent à chaque exécution.

## Étape 2 : nettoyage, entraînement et comparaison des modèles

```bash
python -m data_transformation.nettoyage     # minuscules, ponctuation, emojis, balises
python -m model.modele_lstm                 # LSTM bidirectionnel (CPU, quelques minutes)
python -m model.modele_bert                 # BERT-Mini, 11 M de paramètres (CPU)
python -m model.modele_laya                 # Laya multilingue (fine-tuning réduit, CPU)
python -m model.comparer_modeles            # tableau précision / rappel / temps par requête
```
- Les 3 modèles sont entraînés sur **les mêmes 5 000 messages** (`NB_EXEMPLES_TRAIN` dans
  `data_transformation/evaluation.py`) et évalués sur le même jeu, pour un benchmark équitable.
- Le temps est mesuré **par requête** (messages envoyés un par un, comme dans l'API).
- Résultats : `resultats/<modèle>.json` (un par modèle), puis `resultats/comparaison.md`,
  généré par `comparer_modeles` à partir de ces fichiers.

## Étape 3 : API et déploiement sur GKE

### Tester l'API en local
```powershell
pip install fastapi uvicorn
$env:API_KEY="cle-de-test"; $env:LOG_SALT="sel-de-test"; uvicorn Deployment.api:app
# dans un second terminal :
python Deployment/tester_api.py http://127.0.0.1:8000 cle-de-test
```
Documentation interactive : http://127.0.0.1:8000/docs

### Déployer sur Google Kubernetes Engine (depuis Cloud Shell)
```bash
# 1. Services et dépôt d'images (une seule fois)
gcloud services enable container.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud artifacts repositories create dss --repository-format=docker --location=europe-west1

# 2. Construire l'image (code + modèle Laya) et l'envoyer dans Artifact Registry
gcloud builds submit --config Deployment/cloudbuild.yaml \
  --substitutions=_IMAGE=europe-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/dss/api:v3 \
  --timeout=30m --async .

# 3. Créer le cluster et y enregistrer les secrets (clé API, sel des journaux)
gcloud container clusters create-auto dss-cluster --region europe-west1
gcloud container clusters get-credentials dss-cluster --region europe-west1
kubectl create secret generic dss-secrets \
  --from-literal=API_KEY=$(openssl rand -hex 24) --from-literal=LOG_SALT=$(openssl rand -hex 32)

# 4. Déployer (remplacer MON_PROJET et la version de l'image dans deployment.yaml)
sed -i "s/MON_PROJET/$GOOGLE_CLOUD_PROJECT/; s#/dss/api:v[0-9]*#/dss/api:v3#" Deployment/k8s/deployment.yaml
kubectl apply -f Deployment/k8s/
kubectl get service dss-api          # adresse publique dans EXTERNAL-IP
```

## Étape 4 : sécurité et conformité RGPD

| Mesure | Mise en œuvre |
|---|---|
| Authentification | clé API obligatoire (`X-API-Key`), comparée en temps constant ; 401 sinon |
| Validation des entrées | texte de 1 à 1 000 caractères ; 422 sinon |
| Secrets | Secret Kubernetes, jamais dans le code, l'image ou le dépôt |
| Journaux | une ligne JSON par requête, **sans le texte**, clé remplacée par une empreinte HMAC |
| IAM | moindre privilège (voir le rapport) ; pods de l'API sans aucun droit Google Cloud (Workload Identity) |
| Hébergement | région `europe-west1` (Union européenne) |
| Limite connue | pas de HTTPS dans le cadre du TP |

```bash
# Tests de sécurité et exemples de requêtes sur l'API déployée
python Deployment/tester_api.py http://<EXTERNAL-IP> <clé-API>
kubectl logs deployment/dss-api --tail=20      # journaux pseudonymisés
```

## Étape 5 : simulation de montée en charge

```bash
pip install locust
SCENARIO=montee API_KEY=<clé-API> locust -f Deployment/locustfile.py --headless \
  --host http://<EXTERNAL-IP> --csv resultats/charge_montee --html resultats/charge_montee.html
```
| Scénario (`SCENARIO=`) | Charge | Durée |
|---|---|---|
| `montee` | 5 → 60 utilisateurs par paliers de 2 min | 10 min |
| `stress` | 5 utilisateurs, puis 100 d'un coup | 6 min |
| `panne` | 20 utilisateurs constants ; un pod est supprimé pendant le test | 5 min |

Chaque test affiche un résumé (débit, latence moyenne, P95/P99, taux d'erreur) et génère
un rapport HTML et des CSV dans `resultats/` (`charge_<scénario>*`). Pendant les tests :
`kubectl get hpa dss-api --watch` pour suivre l'autoscaling.

Pour le scénario `panne`, supprimer un pod pendant que Locust tourne :
```bash
kubectl delete $(kubectl get pod -l app=dss-api -o name | head -n 1)
kubectl get pods -l app=dss-api --watch      # Kubernetes recrée le pod (~1 à 3 min : chargement de Laya)
```

## Étape 6 : sécurité et supervision

### Chaîne de supervision
```
pods API (port 9090, interne) ──► Managed Prometheus ──► frontend (proxy, lecture seule) ──► Grafana
        (PodMonitoring, 15 s)                              namespace "supervision"          (pas d'IP publique)
```
| Métrique | Origine | Sert à repérer |
|---|---|---|
| `http_requests_total` (par code HTTP) | `prometheus-fastapi-instrumentator` | pics de 401 (fausses clés), de 422, de 5xx |
| `http_request_duration_highr_seconds` | idem | latence totale, file d'attente sous la charge |
| `inference_latency_seconds` | `api.py` | temps de calcul du modèle seul |
| `dss_score_toxicite` | `api.py` | hausse anormale de la part de messages toxiques (raid, spam) |

Les métriques sont servies sur le port **9090**, que le Service n'expose pas : elles ne sont
lisibles que depuis le cluster. Le tableau de bord « DSS - API » (requêtes par code, latence P95
totale / modèle, CPU par pod, pods en ligne, part de messages toxiques) est chargé
automatiquement au démarrage de Grafana.

### Déployer la supervision (depuis Cloud Shell, après l'étape 3)
```bash
PROJET=$GOOGLE_CLOUD_PROJECT
kubectl create namespace supervision

# 1. Compte de service en LECTURE SEULE sur les métriques (moindre privilège)
gcloud iam service-accounts create gmp-lecteur
gcloud projects add-iam-policy-binding $PROJET \
  --member=serviceAccount:gmp-lecteur@$PROJET.iam.gserviceaccount.com --role=roles/monitoring.viewer
gcloud iam service-accounts add-iam-policy-binding gmp-lecteur@$PROJET.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser --member="serviceAccount:$PROJET.svc.id.goog[supervision/default]"
kubectl annotate serviceaccount default -n supervision \
  iam.gke.io/gcp-service-account=gmp-lecteur@$PROJET.iam.gserviceaccount.com

# 2. Proxy "frontend" de Google (permet à Grafana de lire Managed Prometheus)
curl -s https://raw.githubusercontent.com/GoogleCloudPlatform/prometheus-engine/main/examples/frontend.yaml \
  | sed "s/\$PROJECT_ID/$PROJET/" | kubectl apply -n supervision -f -

# 3. Grafana (mot de passe admin dans un Secret, jamais dans git)
kubectl create secret generic grafana-admin -n supervision \
  --from-literal=mot_de_passe=$(openssl rand -hex 16)
kubectl apply -f Deployment/supervision/grafana.yaml

# 4. Accès privé par tunnel (Cloud Shell : Aperçu Web sur le port 3000)
kubectl port-forward -n supervision svc/grafana 3000:3000
```

### Simuler des attaques et analyser les journaux
```bash
API_KEY=<clé-API> python Deployment/tester_attaques.py http://<EXTERNAL-IP>
```
| Test | Attaque | Résultat attendu |
|---|---|---|
| S8 | injection (`<script>`, SQL, gabarits, `../`) | 200 : traité comme du texte, rien n'est exécuté |
| S9 | insultes déguisées (`1d10t`, `n00b`, `s.t.u.p.i.d`) | comparer les scores : limite du modèle si le score chute |
| Validation | texte de 1 001 caractères, vide, nombre, `null` | 422, jamais 500 |
| S11 | 20 requêtes avec de fausses clés | 401 partout (pas de blocage après plusieurs échecs : limite connue) |

```bash
kubectl logs -l app=dss-api --tail=500 | grep '"statut": 401'   # essais de clés refusés
kubectl logs -l app=dss-api --tail=500 | grep '"statut": 422'   # entrées invalides
```
Chaque ligne contient l'empreinte de l'IP et de la clé : on peut regrouper les requêtes
d'un même client sans jamais connaître son IP ni sa clé.

## Étape 7 : architecture Cloud

Le schéma d'architecture et son texte explicatif sont dans le rapport. Composants :

| Composant | Rôle | Sécurité |
|---|---|---|
| Load Balancer (Service `dss-api`) | IP publique, répartit le trafic entre les pods | seul point d'entrée (port 80) |
| Pods API (Deployment, 2 à 10 via HPA) | FastAPI + Laya, renvoie le score | clé API, validation, aucun droit Google Cloud |
| Secret `dss-secrets` | clé API, sel des journaux | hors du code et du dépôt |
| Artifact Registry | images Docker de l'API | région `europe-west1` |
| Cloud Logging | journaux pseudonymisés (sans le texte) | conservation 30 jours |
| Managed Prometheus + Grafana | métriques et tableau de bord | port 9090 interne, Grafana sans IP publique, lecture seule IAM |

---

## Arrêter le déploiement (coûts)
```bash
kubectl delete -f Deployment/k8s/
kubectl delete namespace supervision          # Grafana + frontend (étape 6)
gcloud container clusters delete dss-cluster --region europe-west1
```
