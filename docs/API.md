# API « Digital Social Score » : documentation

L'API reçoit un message texte et renvoie un **score de toxicité de 0 à 100**.
Elle s'appuie sur le modèle de décision **Laya** (version multilingue), ajusté sur
le jeu de données GameTox (messages de chat de jeu vidéo), et tourne sur
**Google Kubernetes Engine** (région `europe-west1`, Belgique).

---

## 1. Accès

| Élément | Valeur |
|---|---|
| URL de base | `http://<EXTERNAL-IP>` (adresse du Service `dss-api` : `kubectl get service dss-api`) |
| Protocole | HTTP (voir [Limites](#6-limites-connues)) |
| Format | JSON (`Content-Type: application/json`) |
| Documentation interactive | `http://<EXTERNAL-IP>/docs` (générée automatiquement par FastAPI) |

### Authentification
La route `/score` exige une **clé API** dans l'en-tête HTTP `X-API-Key` :

```
X-API-Key: <votre-clé>
```

- La clé est fournie par l'administrateur de l'API. Elle est stockée côté serveur dans
  un Secret Kubernetes, jamais dans le code.
- Sans clé, ou avec une clé invalide, l'API répond **401**.
- Dans la documentation interactive (`/docs`), le bouton **Authorize** permet de
  saisir la clé une fois pour toutes les requêtes.

---

## 2. Routes

### `POST /score` : noter un message
Calcule le score de toxicité d'un texte.

**En-têtes**

| En-tête | Obligatoire | Valeur |
|---|---|---|
| `Content-Type` | oui | `application/json` |
| `X-API-Key` | oui | la clé API |

**Corps de la requête**

| Champ | Type | Contraintes | Description |
|---|---|---|---|
| `texte` | chaîne | 1 à 1 000 caractères | le message à analyser |

```json
{ "texte": "useless noob" }
```

**Réponse (200 OK)**

| Champ | Type | Description |
|---|---|---|
| `score` | nombre (0 à 100) | probabilité, estimée par le modèle, que le message soit toxique, en % |
| `note` | entier (0 à 5) | gravité la plus probable : 0 = sain, 1 = insulte, 2 = autre propos offensant, 3 = haine / harcèlement, 4 = menace, 5 = extrémisme |
| `toxique` | booléen | `true` si `score` ≥ 50 |

```json
{ "score": 98.4, "note": 1, "toxique": true }
```

### `GET /health` : état de l'API
Vérifie que l'API est démarrée et que le modèle est chargé. **Pas de clé requise** :
cette route est utilisée par Kubernetes pour surveiller les pods.

```json
{ "statut": "ok" }
```

---

## 3. Codes de réponse

| Code | Signification | Cause |
|---|---|---|
| **200** | Succès | le score est renvoyé |
| **401** | Non autorisé | clé API absente ou invalide : `{"detail": "Clé API absente ou invalide"}` |
| **422** | Entrée invalide | champ `texte` absent, vide ou de plus de 1 000 caractères |

---

## 4. Interpréter le score

| Score | Lecture |
|---|---|
| proche de 0 | le modèle est sûr que le message est **sain** |
| autour de 50 | le modèle **hésite** (message ambigu, ironie, langue étrangère…) |
| proche de 100 | le modèle est sûr que le message est **toxique** |

Le score mesure **la probabilité qu'un message soit toxique, pas sa gravité**. La gravité
est donnée par `note`, mais elle est peu fiable pour les niveaux élevés : le jeu
d'entraînement contient très peu de menaces ou de propos extrémistes. Une insulte et une
incitation au suicide peuvent ainsi obtenir des scores proches.

---

## 5. Exemples de requêtes et réponses

### Avec `curl` (Linux, macOS, Cloud Shell)
```bash
curl -X POST http://<EXTERNAL-IP>/score \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <votre-clé>" \
  -d '{"texte": "useless noob"}'
```

### Avec PowerShell (Windows)
```powershell
Invoke-RestMethod -Method Post -Uri "http://<EXTERNAL-IP>/score" `
  -Headers @{ "X-API-Key" = "<votre-clé>" } `
  -ContentType "application/json" -Body '{"texte": "useless noob"}'
```

### Avec Python
```python
import requests

reponse = requests.post(
    "http://<EXTERNAL-IP>/score",
    headers={"X-API-Key": "<votre-clé>"},
    json={"texte": "useless noob"},
)
print(reponse.status_code, reponse.json())
