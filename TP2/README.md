# Digital Social Score – TP2 : de la menace à la défense

Suite du [TP1](../TP1/README.md). On attaque l'API de détection de toxicité déployée sur GKE,
on mesure l'impact de l'attaque, puis on met en place une défense, la conformité IA Act et un
pipeline DevSecOps.

**Attaque choisie : extraction de modèle (model stealing).** L'attaquant n'a qu'une clé API
valide ; il interroge `POST /score` et se sert des réponses pour entraîner une copie du modèle.

## Organisation

```
TP2/
├── attack/
│   └── attaque_extraction.py      étapes 2 et 3 : attaque par extraction de modèle
├── resultats/                     générés par le script (voir « Fichiers produits »)
├── requirements.txt               dépendances en plus de celles du TP1
├── TP2_Digital_Social_Score.pdf   énoncé
└── Cours_n°4 / n°5 (*.pdf)        supports de cours
```

## Installation

Depuis la racine du dépôt, dans l'environnement virtuel du TP1 :
```bash
pip install -r TP1/requirements.txt -r TP2/requirements.txt
```

---

## Attaque par extraction de modèle

### Fonctionnement du script
1. **Latence de base** : 30 requêtes envoyées une par une, API au calme.
2. **Référence** : les décisions de l'API (Laya) sur le jeu d'évaluation du TP1
   (`TP1/data_eval/val_clean.csv`), comparées aux vrais labels.
3. **Attaque** : jusqu'à 2 000 messages publics (`TP1/data_train/train_clean.csv`, labels
   ignorés) envoyés avec 8 requêtes en parallèle ; on garde la décision `toxique` de l'API.
4. **Copies** : une copie TF-IDF + régression logistique est entraînée pour chaque budget
   (100, 250, 500, 1 000, 2 000 requêtes) et comparée à Laya sur le jeu d'évaluation.

Si l'API répond 429 ou 503, le script attend de plus en plus longtemps puis réessaie
(5 essais maximum, en respectant l'en-tête `Retry-After`). Il se comporte ainsi comme un
attaquant « patient » face à une limite de débit. Une requête toujours bloquée est comptée
comme bloquée, sans arrêter le script.

### Lancement (depuis la racine du dépôt)
```powershell
$env:API_URL="http://<EXTERNAL-IP>/score" ; $env:API_KEY="<clé-API>"
python TP2/attack/attaque_extraction.py
```
```bash
API_URL=http://<EXTERNAL-IP>/score API_KEY=<clé-API> python TP2/attack/attaque_extraction.py
```
L'URL et la clé passent **uniquement** par des variables d'environnement, jamais dans le code.
Pour attaquer l'API en local, lancer d'abord l'API du TP1 (voir son README) et utiliser
`http://127.0.0.1:8000/score`.

Paramètres modifiables en haut du script : `BUDGETS`, `N_WORKERS` (requêtes en parallèle),
`N_BASELINE`, `TIMEOUT`, `MAX_RETRIES`.

### Fichiers produits (`TP2/resultats/`)

| Fichier | Contenu |
|---|---|
| `metrics.csv` | pour chaque budget : accuracy, précision, taux de faux positifs de la copie, accord avec Laya |
| `metrics.json` | idem + métriques de Laya, latence (moyenne, P95) au calme et pendant l'attaque, requêtes bloquées |
| `extraction_metrics.png` | qualité de la copie selon le nombre de requêtes, avec Laya en référence |
| `latence.png` | latence normale vs pendant l'attaque |
| `cache_reponses_api.json` | réponses déjà obtenues : une relance ne réinterroge pas l'API pour ces messages |

### Mesurer l'effet d'une défense
Une fois la défense déployée, relancer l'attaque **avec une étiquette** :
```powershell
$env:ETIQUETTE="apres_defense"
python TP2/attack/attaque_extraction.py
```
Tous les fichiers prennent le suffixe `_apres_defense` (`metrics_apres_defense.json`, etc.) :
les résultats de l'attaque initiale ne sont pas écrasés. Le cache est lui aussi séparé et
vide au départ, ce qui oblige l'attaque à interroger réellement l'API protégée. Avec le cache
initial, les réponses déjà obtenues feraient croire que la défense ne sert à rien.
