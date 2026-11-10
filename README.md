# TP Digital Social Score – IA & cybersécurité

## Organisation du dépôt

```
IA_Cybersecu/
├── data_train/
│   ├── train_raw.csv            messages bruts GameTox (42 959 lignes)
│   ├── train_anon.csv           anonymisé (généré, étape 1)
│   └── train_clean.csv          anonymisé + nettoyé (généré, étape 2)
├── data_eval/
│   ├── val_raw.csv              messages bruts (5 367 lignes)
│   ├── val_anon.csv             anonymisé (généré)
│   └── val_clean.csv            anonymisé + nettoyé (généré)
├── data_transformation/
│   ├── anonymisation.py         étape 1 : produit les *_anon.csv
│   ├── nettoyage.py             étape 2 : produit les *_clean.csv
│   └── evaluation.py            étape 2 : découpage des données, métriques (importé par model/)
├── model/
│   ├── modele_lstm.py           étape 2 : modèle statistique (LSTM)
│   ├── modele_bert.py           étape 2 : modèle transformer (BERT-Mini)
│   ├── modele_laya.py           étape 2 : modèle de décision (Laya)
│   └── comparer_modeles.py      étape 2 : tableau comparatif
├── Deployment/
│   ├── api.py                   étape 3 : API FastAPI (score 0-100)
│   ├── Dockerfile               étape 3 : image de l'API
│   ├── cloudbuild.yaml          étape 3 : construction de l'image sur Google Cloud
│   └── tester_api.py            étape 3 : exemples de requêtes / réponses
├── modeles/                     modèles entraînés (non versionné, trop lourd)
├── resultats/                   métriques de chaque modèle (JSON)
├── REGISTRE_RGPD.md             registre des traitements
└── TP1_Digital_Social_Score.pdf
```

**Toutes les commandes se lancent depuis la racine du projet**, avec `python -m dossier.script`
(sinon les imports entre dossiers et les chemins des données ne fonctionnent pas).

## Traitement d'un message (anonymisation.py)

```
message brut
   │
   ├─ anonymiser_regex()   e-mail, URL, IP, téléphone  → <EMAIL> <URL> <IP> <PHONE>
   ├─ pseudonymiser()      pseudos de joueurs           → <USER_xxxxxxxx>   (HMAC)
   └─ anonymiser_ner()     prénoms / noms (spaCy)       → <PERSON>
   │
message anonymisé
```

## Étape 1 : anonymisation

```bash
pip install pandas spacy gender-guesser phonenumbers python-dotenv
python -m spacy download en_core_web_sm

# clé secrète de pseudonymisation : dans le fichier .env (non versionné)
#   PSEUDO_KEY=une_longue_chaine_aleatoire

python -m data_transformation.anonymisation
```

Sans `PSEUDO_KEY`, le script tire une clé au hasard : les codes `<USER_...>` changent alors à chaque exécution.

## Étape 2 : nettoyage, entraînement et comparaison des modèles

```bash
pip install -r requirements.txt
python -m data_transformation.nettoyage
python -m model.modele_lstm          # CPU, quelques minutes
python -m model.modele_bert          # BERT-Mini, CPU, ~10 min
python -m model.modele_laya          # fine-tuning réduit (paramètres en haut du fichier)
python -m model.comparer_modeles
```

## Étape 3 : API et déploiement

```bash
# Test local
pip install fastapi uvicorn
uvicorn Deployment.api:app --reload          # documentation : http://127.0.0.1:8000/docs
python Deployment/tester_api.py

# Image Docker en local
docker build -f Deployment/Dockerfile -t digital-social-score .
docker run -p 8080:8080 digital-social-score
python Deployment/tester_api.py http://127.0.0.1:8080
```

Déploiement sur Cloud Run : voir les commandes `gcloud` (Artifact Registry, Cloud Build, Cloud Run).
