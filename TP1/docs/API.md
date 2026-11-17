# API « Digital Social Score » : documentation

L'API reçoit un message texte et renvoie un **score de toxicité de 0 à 100**.
Elle s'appuie sur le modèle de décision **Laya** (version multilingue), ajusté sur
le jeu de données GameTox (messages de chat de jeu vidéo), et tourne sur
**Google Kubernetes Engine** (région `europe-west1`, Belgique).

---

## 1. Accès

| Élément | Valeur |
|---|---|
| URL de base | `http://34.36.74.177` (adresse de l'Ingress, derrière le WAF : `kubectl get ingress dss-api`) |
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
| `toxique` | booléen | `true` si le message est jugé toxique (probabilité ≥ 50 %) |
| `niveau` | entier (0, 25, 50, 75 ou 100) | probabilité de toxicité, arrondie au palier de 25 le plus proche |

```json
{ "toxique": true, "niveau": 100 }
```

Le score exact n'est volontairement pas renvoyé : il aidait un attaquant à copier le
modèle (attaque par extraction). Il reste connu en interne (journaux, métriques).

**Limite de débit** : 60 requêtes par minute et par clé API. Au-delà, l'API répond
**429** avec un en-tête `Retry-After` (secondes à attendre). La limite est comptée par
pod : avec plusieurs pods, la limite réelle est un peu plus haute.

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
| **429** | Trop de requêtes | plus de 60 requêtes par minute avec la même clé ; réessayer après `Retry-After` secondes |

---

## 4. Interpréter le score

| `niveau` | Lecture |
|---|---|
| 0 ou 25 | le modèle juge le message **sain** |
| 50 | le modèle **hésite** (message ambigu, ironie, langue étrangère…) |
| 75 ou 100 | le modèle juge le message **toxique** |

Le niveau mesure **la probabilité qu'un message soit toxique, pas sa gravité**. Une insulte
et une incitation au suicide peuvent ainsi obtenir le même niveau.

Avant l'analyse, le texte est « démasqué » : leetspeak (`1d10t`), lettres espacées
(`i d i o t`), lettres cyrilliques déguisées et caractères invisibles sont remis en clair.
Un message déguisé obtient donc le même verdict que sa version normale.

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
```

### Script de test fourni
`Deployment/tester_api.py` envoie une série de requêtes (sécurité et exemples) :
```bash
python Deployment/tester_api.py http://<EXTERNAL-IP> <votre-clé>
```

### Résultats obtenus sur l'API déployée (GKE, image `v3`)

**Tests de sécurité**

| Requête | Code | Réponse |
|---|---|---|
| `"gg wp"` **sans clé** | 401 | `{"detail": "Clé API absente ou invalide"}` |
| `"gg wp"` avec une **mauvaise clé** | 401 | `{"detail": "Clé API absente ou invalide"}` |
| `""` (texte vide) | 422 | `{"detail": [{"type": "string_too_short", "loc": ["body", "texte"], "msg": "String should have at least 1 character", ...}]}` |

**Exemples de messages** (avec une clé valide)

| Message | Catégorie | Score | Note | Toxique |
|---|---|---|---|---|
| `gg wp team` | sain | 0,8 | 0 | non |
| `nice shot, well played` | sain | 1,5 | 0 | non |
| `gg ez` | ambigu | 0,8 | 0 | non |
| `ty for nothing` | ambigu (ironie) | 13,5 | 0 | non |
| `wtf was that` | ambigu (agacement) | 61,6 | 1 | oui |
| `you're mad lol` | ambigu (taquinerie) | 90,6 | 1 | oui |
| `noob` | ambigu | 94,0 | 1 | oui |
| `cyka blyat` | juron russe | 4,0 | 0 | non |
| `useless noob` | toxique | 98,4 | 1 | oui |
| `you are so stupid, uninstall` | toxique | 95,9 | 1 | oui |
| `kys idiot` | toxique (incitation au suicide) | 96,4 | 1 | oui |

Temps de réponse observé : environ **230 ms** par requête sur l'API déployée (1 cœur par pod).

**Lecture des résultats :** les messages sains et clairement toxiques sont bien distingués,
et des scores intermédiaires apparaissent sur les cas ambigus (« wtf was that » : 61,6 ;
« ty for nothing » : 13,5). Le modèle reproduit les choix d'annotation du jeu de données
(« noob » est jugé toxique, « gg ez » ne l'est pas). Limites : un juron russe écrit en
alphabet latin n'est pas détecté, et la gravité n'est pas distinguée (toutes les insultes
reçoivent la note 1, y compris « kys »).

---

## 6. Limites connues

- **Pas de HTTPS** : le texte et la clé API transitent en clair sur le réseau. En production,
  l'API serait placée derrière un Ingress GKE avec un certificat TLS géré par Google.
- **Capacité** : environ 5 requêtes par seconde avec 2 pods. Au-delà, les requêtes attendent
  et la latence augmente (voir le rapport de simulation de charge).
- **Langues** : le modèle est surtout fiable sur l'anglais.

## 7. Données personnelles

- Le texte reçu est analysé **en mémoire** et n'est **jamais stocké ni journalisé**.
- Chaque requête produit une ligne de journal pseudonymisée : route, code de réponse, durée,
  score, longueur du texte, et une empreinte HMAC de la clé API (jamais la clé elle-même).
- Les journaux sont conservés 30 jours dans Cloud Logging (durée par défaut).
- Voir `REGISTRE_RGPD.md` (traitement n° 2 : API en production).
