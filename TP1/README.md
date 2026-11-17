# Digital Social Score – TP1

API qui détecte la toxicité d'un message de chat et renvoie un verdict (toxique ou non) avec
un niveau de 0 à 100. Modèle Laya, déployé sur Google Kubernetes Engine.

- Documentation de l'API : [`docs/API.md`](docs/API.md)
- Registre RGPD : [`REGISTRE_RGPD.md`](REGISTRE_RGPD.md)

## Organisation

```
TP1/
├── data_train/, data_eval/   données GameTox : brutes, anonymisées, nettoyées
├── data_transformation/      anonymisation (étape 1), nettoyage (étape 2)
├── model/                    LSTM, BERT-Mini, Laya + comparaison (étape 2)
├── Deployment/
│   ├── api.py                API FastAPI
│   ├── normalisation.py      défense TP2 : démasque les insultes déguisées
│   ├── defenses_api.py       défense TP2 : limite de débit, réponse appauvrie
│   ├── Dockerfile            image de l'API
│   ├── k8s/                  déploiement GKE (pods, service, autoscaling, métriques)
│   ├── supervision/          Grafana
│   ├── tester_api.py         requêtes de test
│   ├── tester_attaques.py    simulation d'attaques
│   └── locustfile.py         tests de charge
├── docs/API.md               documentation de l'API
└── resultats/                métriques des modèles
```

Pas dans le dépôt : `modeles/` (trop lourd), `.env` (clé de pseudonymisation), et les secrets
de production (dans le Secret Kubernetes `dss-secrets`).

## Installation

Toutes les commandes se lancent depuis `TP1/`.
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1                # Windows ; Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Étape 1 : anonymisation

```bash
python -m data_transformation.anonymisation   # clé PSEUDO_KEY dans .env
```
E-mails, URL, IP et téléphones → balises ; pseudos → empreinte HMAC ; prénoms → `<PERSON>`.

## Étape 2 : modèles

```bash
python -m data_transformation.nettoyage
python -m model.modele_lstm
python -m model.modele_bert
python -m model.modele_laya
python -m model.comparer_modeles          # écrit resultats/comparaison.md
```

## Étape 3 : API

**En local**
```powershell
$env:API_KEY="cle-de-test"; $env:LOG_SALT="sel-de-test"; uvicorn Deployment.api:app
python Deployment/tester_api.py http://127.0.0.1:8000 cle-de-test
```

**Sur GKE** (Cloud Shell, première installation)
```bash
gcloud artifacts repositories create dss --repository-format=docker --location=europe-west1
gcloud builds submit --config Deployment/cloudbuild.yaml \
  --substitutions=_IMAGE=europe-west1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/dss/api:v1 .
gcloud container clusters create-auto dss-cluster --region europe-west1
kubectl create secret generic dss-secrets \
  --from-literal=API_KEY=$(openssl rand -hex 24) --from-literal=LOG_SALT=$(openssl rand -hex 32)
kubectl apply -f Deployment/k8s/
kubectl get service dss-api                # IP publique : EXTERNAL-IP
```
Les mises à jour suivantes sont déployées par le pipeline GitHub Actions (voir [TP2](../TP2/README.md)).

**Requêtes de test**
```bash
curl <URL>/health                                                     # 200
curl -X POST <URL>/score -H "Content-Type: application/json" \
  -H "X-API-Key: <clé>" -d '{"texte": "useless noob"}'                # 200 {"toxique": true, "niveau": 100}
curl -X POST <URL>/score -H "Content-Type: application/json" \
  -d '{"texte": "gg wp"}'                                             # 401 : pas de clé
curl -X POST <URL>/score -H "Content-Type: application/json" \
  -H "X-API-Key: <clé>" -d '{"texte": ""}'                            # 422 : texte vide
```
Au-delà de 60 requêtes par minute avec la même clé : 429.

## Étape 4 : sécurité et RGPD

| Mesure | Mise en œuvre |
|---|---|
| Authentification | clé API (`X-API-Key`), sinon 401 |
| Validation | texte de 1 à 1 000 caractères, sinon 422 |
| Secrets | Secret Kubernetes, jamais dans le code |
| Journaux | sans le texte, IP et clé pseudonymisées (HMAC) |
| Hébergement | `europe-west1` (UE) |

## Étape 5 : montée en charge

```bash
SCENARIO=montee API_KEY=<clé> locust -f Deployment/locustfile.py --headless \
  --host http://<EXTERNAL-IP> --html resultats/charge_montee.html
```
Scénarios : `montee` (5 → 60 utilisateurs), `stress` (pic à 100), `panne` (un pod supprimé
pendant le test).

## Étape 6 : supervision et attaques

```bash
# Supervision : Managed Prometheus + Grafana (namespace "supervision", sans IP publique)
kubectl create namespace supervision
kubectl create secret generic grafana-admin -n supervision --from-literal=mot_de_passe=$(openssl rand -hex 16)
kubectl apply -f Deployment/supervision/grafana.yaml
kubectl port-forward -n supervision svc/grafana 3000:3000

# Attaques (injection, insultes déguisées, entrées invalides, fausses clés)
API_KEY=<clé> python Deployment/tester_attaques.py http://<EXTERNAL-IP>
```
Grafana lit les métriques via le proxy « frontend » de Google Managed Prometheus, installé à
part avec un compte de service en lecture seule (`roles/monitoring.viewer`).

## Étape 7 : architecture

Schéma et explications dans le rapport.

## Arrêter (coûts)

```bash
kubectl delete -f Deployment/k8s/ && kubectl delete namespace supervision
gcloud container clusters delete dss-cluster --region europe-west1
```
