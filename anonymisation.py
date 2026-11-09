"""
TP1 - Étape 1 : anonymisation des données
    - regex  : URL + adresses e-mail
    - NER    : prénoms (spaCy, entités PERSON) confirmés par un dictionnaire de
               prénoms (gender-guesser, ~40 000 prénoms internationaux)

Pré-requis : pip install pandas spacy gender-guesser
             python -m spacy download en_core_web_sm
Usage      : python anonymisation.py
Entrée     : data_train/train.csv, data_eval/val.csv, data_test/test_index_text.csv
Sortie     : data_anon/<même nom>.csv  (colonne "message" anonymisée)
"""

import re
from collections import Counter
from pathlib import Path

import gender_guesser.detector as gender
import pandas as pd
import spacy

# ---------------------------------------------------------------------------
# 1. Expressions régulières (données à format fixe)
# ---------------------------------------------------------------------------

# Adresse e-mail : partie_locale@domaine.extension
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}")

# URL :
#   - commençant par http:// , https:// ou www.
#   - OU domaine nu avec une extension connue (ex : twitch.tv/xxx, youtube.com)
URL_RE = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|tv|gg|io|fr|ru|pl|de|eu|cz|ua|be)\b(?:/\S*)?",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# 2. NER spaCy (prénoms)
# ---------------------------------------------------------------------------
# Modèle pré-entraîné anglais (réseau de neurones entraîné sur OntoNotes).
# On désactive le parser et le lemmatizer : inutiles ici, et ça accélère.
nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])

# Problème constaté : sur ce chat de jeu (messages courts, minuscules, multilingues),
# spaCy étiquette PERSON énormément de mots qui n'en sont pas : "omg", "moron",
# "idiot", "сука", des noms de chars ("leo", "kunze")...
# Les remplacer détruirait le signal de toxicité. On CONFIRME donc chaque
# détection avec un dictionnaire de prénoms : la bibliothèque gender-guesser
# (~40 000 prénoms de nombreux pays). Elle sert à deviner le genre d'un prénom ;
# si elle répond "unknown", le mot n'est pas un prénom connu.
detecteur_prenoms = gender.Detector()

# Mots à ne jamais remplacer, même s'ils sont dans le dictionnaire de prénoms :
#   - noms de chars / mots du jeu
#   - mots courants qui sont aussi des prénoms
#   - personnalités publiques (cibles de haine politique, pas des personnes
#     privées du dataset -> on garde le signal)
# À COMPLÉTER après lecture des exemples AVANT/APRÈS affichés par le script.
EXCLUSIONS = {
    # chars / jeu
    "leo", "lee", "emil", "rudy", "grant", "jackson", "sherman", "patton",
    "lorraine", "kunze", "chaffee", "pershing", "churchill", "matilda",
    "valentine", "archer", "ferdinand", "walker", "sheridan", "lynx",
    # mots courants
    "max", "will", "mark", "rose", "guy", "nick", "may", "art", "don", "bill",
    "pat", "ray", "joy", "hope", "grace", "frank", "chase", "dean", "drew",
    "jack", "jesus", "god", "noble", "royal", "ace", "king",
    # personnalités publiques
    "putin", "vladimir", "stalin", "hitler", "zelensky",
}


def est_prenom(token) -> bool:
    """Vrai si le token est un prénom connu du dictionnaire et non exclu."""
    mot = token.lower_
    if mot in EXCLUSIONS or not token.is_alpha or len(mot) < 3:
        return False
    # gender-guesser attend une majuscule initiale : "vlad" -> "Vlad"
    return detecteur_prenoms.get_gender(mot.capitalize()) != "unknown"


def anonymiser_ner(doc):
    """
    Remplace les prénoms détectés dans un Doc spaCy par <PERSON>.

    Deux cas :
      a) spaCy trouve une entité PERSON qui contient un prénom du dictionnaire
         -> on remplace le prénom ET les noms propres qui l'accompagnent
            ("John Smith" -> "<PERSON>")
      b) spaCy ne trouve rien (fréquent en minuscules : "its vlad lol")
         mais le mot est dans le dictionnaire -> on le remplace quand même

    Retourne : (texte anonymisé, liste des entités PERSON rejetées)
    """
    a_remplacer = set()   # indices des tokens à remplacer
    rejetees = []         # entités PERSON de spaCy non confirmées (pour le rapport)

    # a) entités détectées par le NER
    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        if any(est_prenom(t) for t in ent):
            for t in ent:
                if est_prenom(t) or t.pos_ == "PROPN":
                    a_remplacer.add(t.i)
        else:
            rejetees.append(ent.text)

    # b) prénoms ratés par le NER
    for t in doc:
        if est_prenom(t):
            a_remplacer.add(t.i)

    # Reconstruction du texte en partant de la fin (les positions restent valides)
    texte = doc.text
    for i in sorted(a_remplacer, reverse=True):
        t = doc[i]
        texte = texte[: t.idx] + "<PERSON>" + texte[t.idx + len(t.text):]
    # "<PERSON> <PERSON>" -> "<PERSON>" (prénom + nom = une seule personne)
    texte = re.sub(r"<PERSON>(\s+<PERSON>)+", "<PERSON>", texte)
    return texte, rejetees


# ---------------------------------------------------------------------------
# 3. Pipeline complet
# ---------------------------------------------------------------------------

def anonymiser_regex(texte: str) -> str:
    """Remplace les e-mails et les URL par une balise générique."""
    texte = str(texte)
    # L'e-mail en premier : sinon "jean@gmail.com" serait pris en partie pour une URL
    texte = EMAIL_RE.sub("<EMAIL>", texte)
    texte = URL_RE.sub("<URL>", texte)
    return texte


def anonymiser_serie(messages):
    """Regex puis NER sur une liste de messages. nlp.pipe traite par lots (rapide)."""
    textes = [anonymiser_regex(m) for m in messages]
    resultats, rejetees = [], Counter()
    for doc in nlp.pipe(textes, batch_size=1000):
        texte, rej = anonymiser_ner(doc)
        resultats.append(texte)
        rejetees.update(rej)
    return resultats, rejetees


# ---------------------------------------------------------------------------
# 4. Application aux fichiers du dataset
# ---------------------------------------------------------------------------

FICHIERS = [
    "data_train/train.csv",
    "data_eval/val.csv",
    "data_test/test_index_text.csv",
]
DOSSIER_SORTIE = Path("data_anon")

if __name__ == "__main__":
    DOSSIER_SORTIE.mkdir(exist_ok=True)
    total_rejetees = Counter()

    for chemin in FICHIERS:
        df = pd.read_csv(chemin)
        df["message_anon"], rejetees = anonymiser_serie(df["message"])
        total_rejetees.update(rejetees)

        # Comparaison avant / après
        modifies = df[df["message"] != df["message_anon"]]
        print(f"\n=== {chemin} : {len(modifies)} messages modifiés sur {len(df)}")
        for balise in ["<EMAIL>", "<URL>", "<PERSON>"]:
            print(f"  {balise:9}:", modifies["message_anon"].str.count(balise).sum())
        for avant, apres in modifies[["message", "message_anon"]].head(10).values:
            print(f"  AVANT : {avant}\n  APRÈS : {apres}\n")

        # Sauvegarde : on remplace la colonne d'origine par la version anonymisée
        df["message"] = df["message_anon"]
        df.drop(columns="message_anon").to_csv(
            DOSSIER_SORTIE / Path(chemin).name, index=False
        )

    # Justification du filtrage : ce que spaCy seul aurait remplacé à tort
    print("\n=== Entités PERSON de spaCy REJETÉES (non confirmées par le dictionnaire)")
    print(f"  {sum(total_rejetees.values())} détections rejetées, top 25 :")
    for mot, n in total_rejetees.most_common(25):
        print(f"    {n:4}  {mot}")

    print(f"\nFichiers anonymisés écrits dans {DOSSIER_SORTIE}/")
