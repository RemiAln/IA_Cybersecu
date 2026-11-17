# Digital Social Score – TP2

Suite du [TP1](../TP1/README.md) : attaque du modèle, défense, IA Act et pipeline DevSecOps.

## Où sont les fichiers

| Élément | Emplacement |
|---|---|
| Attaque (extraction de modèle) | [`TP2/attack/attaque_extraction.py`](attack/attaque_extraction.py) |
| Résultats de l'attaque | `TP2/resultats/` |
| Défense anti-évasion (normalisation du texte) | [`TP1/Deployment/normalisation.py`](../TP1/Deployment/normalisation.py) |
| Défense anti-extraction (limite de débit, réponse appauvrie) | [`TP1/Deployment/defenses_api.py`](../TP1/Deployment/defenses_api.py) |
| Pipeline CI/CD | [`.github/workflows/devsecops.yml`](../.github/workflows/devsecops.yml) |

Les défenses sont dans `TP1/Deployment/` car elles font partie de l'API : elles sont copiées
dans l'image Docker avec `api.py`.

## Installation

Depuis la racine du dépôt :
```bash
pip install -r TP1/requirements.txt -r TP2/requirements.txt
```

## Attaque

```powershell
$env:API_URL="http://<EXTERNAL-IP>/score" ; $env:API_KEY="<clé>"
python TP2/attack/attaque_extraction.py
```
Le script interroge l'API, entraîne une copie du modèle (100 à 2 000 requêtes) et mesure sa
ressemblance avec Laya, ainsi que la latence. Résultats dans `TP2/resultats/` : `metrics.csv`,
`metrics.json` et graphiques.

**Après la défense**, relancer avec une étiquette, pour ne pas écraser les premiers résultats :
```powershell
$env:ETIQUETTE="apres_defense" ; python TP2/attack/attaque_extraction.py
```

## Défenses

| Défense | Effet |
|---|---|
| Normalisation | leetspeak, lettres espacées, homoglyphes et caractères invisibles remis en clair avant le modèle |
| Limite de débit | 60 requêtes par minute et par clé, puis 429 |
| Réponse appauvrie | verdict + niveau arrondi (0, 25, 50, 75, 100) au lieu du score exact |

```bash
python TP1/Deployment/normalisation.py      # test de la normalisation, sans l'API
```

## Pipeline CI/CD

| Job | Quand | Étapes |
|---|---|---|
| Vérification | chaque push / PR | lint, pip-audit, gitleaks, Trivy (configuration) |
| Déploiement | push sur `main` | build, scan Trivy de l'image, push Artifact Registry, mise à jour GKE |

Variables GitHub nécessaires (*Settings → Secrets and variables → Actions → Variables*) :
`GCP_PROJECT_ID`, `GCP_SA_DEPLOY`, `GCP_WIF_PROVIDER`, `MODELE_IMAGE` (image existante
contenant le modèle, ex. `api:v3`).
