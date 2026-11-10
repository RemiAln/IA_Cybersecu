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
