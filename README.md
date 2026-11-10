# TP Digital Social Score – IA & cybersécurité

## Organisation du dépôt

```
IA_Cybersecu/
├── data_train/
│   ├── train_raw.csv        messages bruts GameTox (42 959 lignes)
│   └── train_anon.csv       même fichier, anonymisé (généré)
├── data_eval/
│   ├── val_raw.csv          messages bruts (5 367 lignes)
│   └── val_anon.csv         même fichier, anonymisé (généré)
├── anonymisation.py         étape 1 : produit les *_anon.csv
├── comparaison.py           étape 1 : contrôle avant / après (lecture seule)
├── REGISTRE_RGPD.md         registre des traitements
├── nettoyage.py             étape 2 : nettoyage des textes (LSTM / transformers)
├── evaluation.py            étape 2 : découpage des données, score 0-100, métriques
├── modele_lstm.py           étape 2 : modèle statistique (LSTM)
├── modele_bert.py           étape 2 : modèle transformer (DistilBERT multilingue)
├── modele_laya.py           étape 2 : modèle de décision (Laya)
├── comparer_modeles.py      étape 2 : tableau comparatif
├── etape2_gcp.ipynb         étape 2 : lancement sur GPU (GCP)
├── resultats/               métriques de chaque modèle (JSON)
└── TP1_Digital_Social_Score.pdf
```

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

## Lancer l'étape 1

```bash
pip install pandas spacy gender-guesser phonenumbers
python -m spacy download en_core_web_sm

# clé secrète de pseudonymisation : à garder hors du dépôt
set PSEUDO_KEY=une_longue_chaine_aleatoire      # Windows (cmd)
export PSEUDO_KEY=une_longue_chaine_aleatoire   # Linux / macOS

python anonymisation.py
python comparaison.py
```

Sans `PSEUDO_KEY`, le script tire une clé au hasard : les codes `<USER_...>` changent alors à chaque exécution.

## Étape 2 : entraîner et comparer les modèles

```bash
pip install -r requirements.txt
python modele_lstm.py               # tourne sur CPU (~1 min)
python modele_bert.py               # BERT-Mini, tourne sur CPU
python modele_laya.py               # fine-tuning réduit (paramètres en haut du fichier)
python comparer_modeles.py
```

Sur GCP : ouvrir `etape2_gcp.ipynb` dans Colab Enterprise ou Vertex AI Workbench (runtime GPU T4).
Les modèles entraînés sont écrits dans `modeles/` (non versionné, trop lourd).
