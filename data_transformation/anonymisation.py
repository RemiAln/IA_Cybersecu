# TP1 - Étape 1 : anonymisation des données
# Usage : python -m data_transformation.anonymisation     (depuis la racine du projet)

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
from collections import Counter
from pathlib import Path

import gender_guesser.detector as gender
import pandas as pd
import phonenumbers
import spacy

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 1. Expressions régulières (données à format fixe)
# ---------------------------------------------------------------------------

# Adresse e-mail : partie_locale@domaine.extension
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}")

# URL :
#   - commençant par http:// , https:// ou www.
#   - OU domaine nu avec une extension connue (ex : twitch.tv/xxx, youtube.com)
#   Après "www." on exige un vrai domaine ("www.site.com"), sinon "Awww... show"
#   serait pris pour une URL. Le port éventuel (":31040") fait partie de l'URL.
URL_RE = re.compile(
    r"(?:https?://\S+|www\.[\w-]+\.\S+)"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|tv|gg|io|fr|ru|pl|de|eu|cz|ua|be)\b"
    r"(?::\d{2,5})?(?:/\S*)?",
    re.IGNORECASE,
)

# Adresse IPv4 : 4 nombres de 0 à 255 séparés par des points (ex : 192.168.1.10)
# Chaque nombre est contrôlé par la regex pour éviter "999.999.999.999".
OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4_RE = re.compile(rf"(?<![\d.]){OCTET}(?:\.{OCTET}){{3}}(?![\d.])")

# Adresse IPv6 : groupes hexadécimaux séparés par ":" (ex : 2001:db8::1).
# La regex attrape des CANDIDATS ; on valide ensuite avec le module standard
# ipaddress, pour ne pas confondre avec une heure comme "12:30:45".
IPV6_CANDIDAT_RE = re.compile(r"(?<![\w:])[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}(?![\w:])")


def remplacer_ipv6(match):
    candidat = match.group(0)
    # Un smiley comme "D::D:D" est une IPv6 techniquement valide (D est un
    # chiffre hexadécimal). Une vraie adresse contient au moins un chiffre.
    if not re.search(r"\d", candidat):
        return candidat
    try:
        ipaddress.IPv6Address(candidat)
        return "<IP>"
    except ValueError:
        return candidat          # pas une vraie IPv6 -> on laisse le texte


# ---------------------------------------------------------------------------
# 1 bis. Numéros de téléphone (bibliothèque phonenumbers = libphonenumber de Google)
# ---------------------------------------------------------------------------
# Une regex maison attraperait "9999999999" ou des dates. phonenumbers connaît
# les plans de numérotation de chaque pays et vérifie que le numéro est valide.
#   - REGIONS : pays utilisés pour interpréter les numéros SANS indicatif
#     (ex : "06 12 34 56 78" n'est valide qu'en France). Les numéros avec
#     indicatif (+33, +7, +1...) sont reconnus quelle que soit la région.
#   - STRICT_GROUPING : les chiffres doivent être groupés comme un vrai numéro.
#     Ça élimine les faux positifs du dataset (une date "05.05.2023 0",
#     une suite "62 65 6565 95").
REGIONS_TEL = ["FR", "GB", "US", "DE", "PL", "RU"]


def anonymiser_telephones(texte: str) -> str:
    """Remplace les numéros de téléphone valides par <PHONE>."""
    positions = set()
    for region in REGIONS_TEL:
        for m in phonenumbers.PhoneNumberMatcher(
            texte, region, leniency=phonenumbers.Leniency.STRICT_GROUPING
        ):
            positions.add((m.start, m.end))
    # Remplacement en partant de la fin ; on saute les détections qui se
    # chevauchent (le même numéro trouvé via deux régions)
    fin_precedente = len(texte) + 1
    for debut, fin in sorted(positions, key=lambda p: (-p[0], -p[1])):
        if fin <= fin_precedente:
            texte = texte[:debut] + "<PHONE>" + texte[fin:]
            fin_precedente = debut
    return texte

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

# Problème constaté en test : gender-guesser contient des prénoms du monde entier,
# dont beaucoup sont aussi des mots courants ("you", "the", "are", "can", "arty",
# "win", "man"...). Deux filtres supplémentaires :
#   1) les mots outils (stop words) de spaCy ne sont jamais des prénoms ;
#   2) un mot présent dans beaucoup de messages du corpus est du vocabulaire
#      (ou du jargon du jeu : "arty", "lowe", "manti"), pas le prénom d'une
#      personne précise. Le seuil est un compromis à justifier dans le rapport.
SEUIL_FREQUENCE = 10          # nb de messages au-delà duquel un mot est "courant"
FREQ_CORPUS = Counter()       # rempli par calculer_frequences() avant l'anonymisation


def calculer_frequences(messages):
    """Compte, pour chaque mot (en minuscules), le nombre de messages qui le contiennent."""
    FREQ_CORPUS.clear()
    for m in messages:
        FREQ_CORPUS.update(set(re.findall(r"\w+", str(m).lower())))


def est_prenom(token) -> bool:
    """Vrai si le token est un prénom connu du dictionnaire et pas un mot courant."""
    mot = token.lower_
    if not token.is_alpha or len(mot) < 3:
        return False
    if token.is_stop or FREQ_CORPUS[mot] >= SEUIL_FREQUENCE:
        return False
    # gender-guesser attend une majuscule initiale : "vlad" -> "Vlad"
    return detecteur_prenoms.get_gender(mot.capitalize()) != "unknown"


def anonymiser_ner(doc):
    """
    Remplace les prénoms par <PERSON>.

    spaCy trouve une entité PERSON qui contient un prénom du dictionnaire
    -> on remplace le prénom ET le nom propre qui le suit
       ("John Smith" -> "<PERSON>")
    Si spaCy ne détecte rien (fréquent en minuscules : "its vlad lol"),
    le prénom n'est PAS remplacé : limite assumée du NER.

    Retourne : (texte anonymisé, entités PERSON rejetées)
    """
    a_remplacer = set()      # indices des tokens à remplacer
    rejetees = []            # détections spaCy non confirmées (pour le rapport)

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        prenoms = [t for t in ent if est_prenom(t)]
        if not prenoms:
            rejetees.append(ent.text)
            continue
        for t in prenoms:
            a_remplacer.add(t.i)
            # Le nom de famille est le mot juste après le prénom ("jacek jaworek").
            # Avant, on remplaçait TOUS les noms propres de l'entité : sur
            # "tu ecris ce que tu veux", "que" (prénom du dictionnaire) entraînait
            # la suppression de 6 mots. On se limite maintenant au mot suivant.
            suivant = doc[t.i + 1] if t.i + 1 < ent.end else None
            if suivant is not None and suivant.pos_ == "PROPN" and suivant.is_alpha \
                    and not suivant.is_stop:
                a_remplacer.add(suivant.i)

    # Reconstruction du texte en partant de la fin (les positions restent valides)
    texte = doc.text
    for i in sorted(a_remplacer, reverse=True):
        t = doc[i]
        texte = texte[: t.idx] + "<PERSON>" + texte[t.idx + len(t.text):]
    # "<PERSON> <PERSON>" -> "<PERSON>" (prénom + nom = une seule personne)
    texte = re.sub(r"<PERSON>(\s*<PERSON>)+", "<PERSON>", texte)
    return texte, rejetees


# ---------------------------------------------------------------------------
# 2 bis. Pseudos de joueurs -> pseudonymisation
# ---------------------------------------------------------------------------
# Un pseudo identifie un joueur de façon indirecte (profil public, chaîne
# Twitch...) : c'est une donnée personnelle au sens du RGPD. On ne le supprime
# pas, on le remplace par un code : le même pseudo donne toujours le même code,
# ce qui garde l'information "c'est le même joueur" pour le modèle.
# Le code est un HMAC-SHA256 (hash avec clé secrète) : sans la clé, impossible
# de retrouver le pseudo, même en testant une liste de pseudos connus.
CLE_PSEUDO = os.environ.get("PSEUDO_KEY", "").encode()
if not CLE_PSEUDO:
    CLE_PSEUDO = secrets.token_bytes(32)
    print("ATTENTION : PSEUDO_KEY non définie, clé aléatoire utilisée "
          "(les codes changeront à chaque exécution)")

# Trois formes de pseudos repérées dans le chat de World of Tanks :
#   a) message automatique du jeu, en début de message :
#      "Pseudo (Char), you are blocking..." ou "Pseudo[CLAN] (Char), ..."
PSEUDO_CHAR_RE = re.compile(r"^(\w{3,24})(?=(?:\[[^\]]*\])?\s\([^()]{2,30}\))")
#   b) mention "@Pseudo" (mais pas "f@cking" : il faut un espace ou le début avant)
PSEUDO_AT_RE = re.compile(r"(?<!\S)@(\w{3,24})")
#   c) mot avec underscore ("andron_65_1") ou lettres + chiffres ("gregohri1980").
#      Volontairement étroit : "1D1OT", "B1TCH" (insultes en leet speak) ou
#      "FV207" (nom de char) ne doivent PAS disparaître.
PSEUDO_FORME_RE = re.compile(
    r"(?<![\w<])(?=\w*[A-Za-z])(\w*_\w*|[A-Za-z]{4,}\d{2,})(?!\w)"
)


def code_pseudo(pseudo: str) -> str:
    empreinte = hmac.new(CLE_PSEUDO, pseudo.lower().encode(), hashlib.sha256)
    return f"<USER_{empreinte.hexdigest()[:8]}>"


def pseudonymiser(texte: str) -> str:
    """Remplace les pseudos par <USER_xxxxxxxx>."""
    def remplacer(m, prefixe=""):
        pseudo = m.group(1)
        # Un mot fréquent dans le corpus est du vocabulaire ("Arta (M12)"),
        # pas un pseudo : même seuil que pour les prénoms.
        # Moins de 4 caractères hors "_" : émoticône ("T_T", "x_X") ou insulte
        # censurée ("sh_t"), pas un pseudo.
        if FREQ_CORPUS[pseudo.lower()] >= SEUIL_FREQUENCE or len(pseudo.replace("_", "")) < 4:
            return m.group(0)
        return prefixe + code_pseudo(pseudo)

    texte = PSEUDO_AT_RE.sub(lambda m: remplacer(m, "@"), texte)
    texte = PSEUDO_CHAR_RE.sub(remplacer, texte)
    texte = PSEUDO_FORME_RE.sub(remplacer, texte)
    return texte


# ---------------------------------------------------------------------------
# 3. Pipeline complet
# ---------------------------------------------------------------------------

def anonymiser_regex(texte: str) -> str:
    """Remplace e-mails, URL, IP et téléphones par une balise générique."""
    texte = str(texte)
    texte = EMAIL_RE.sub("<EMAIL>", texte)
    texte = URL_RE.sub("<URL>", texte)          # une URL contenant une IP part ici
    texte = IPV4_RE.sub("<IP>", texte)
    texte = IPV6_CANDIDAT_RE.sub(remplacer_ipv6, texte)
    texte = anonymiser_telephones(texte)        # après IP : 192.168.1.10 n'est pas un tél.
    return texte


def anonymiser_serie(messages):
    """Regex, pseudos puis NER sur une liste de messages. nlp.pipe traite par lots."""
    textes = [pseudonymiser(anonymiser_regex(m)) for m in messages]
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
    "data_train/train_raw.csv",
    "data_eval/val_raw.csv",
]


def chemin_sortie(chemin_entree: str) -> Path:
    """
    Fichier de sortie dans le même dossier, nommé <jeu>_anon.csv :
      data_train/train_raw.csv -> data_train/train_anon.csv
      data_eval/val_raw.csv    -> data_eval/val_anon.csv
    """
    entree = Path(chemin_entree)
    jeu = entree.name.split("_")[0]          # "train", "val" ou "test"
    sortie = entree.with_name(f"{jeu}_anon.csv")
    # Sécurité : on refuse d'écraser le fichier source
    if sortie.resolve() == entree.resolve():
        raise ValueError(f"Le fichier de sortie écraserait la source : {entree}")
    return sortie

if __name__ == "__main__":
    total_rejetees = Counter()

    # Fréquence des mots sur TOUT le corpus (train + val), utilisée pour ne pas
    # prendre un mot courant ou du jargon du jeu pour un prénom.
    # Les CSV sont seulement LUS ici ; ils ne sont jamais modifiés.
    calculer_frequences(
        pd.concat([pd.read_csv(f)["message"] for f in FICHIERS])
    )

    for chemin in FICHIERS:
        df = pd.read_csv(chemin)
        df["message_anon"], rejetees = anonymiser_serie(df["message"])
        total_rejetees.update(rejetees)

        # Comparaison avant / après
        modifies = df[df["message"] != df["message_anon"]]
        print(f"\n=== {chemin} : {len(modifies)} messages modifiés sur {len(df)}")
        for balise in ["<EMAIL>", "<URL>", "<IP>", "<PHONE>", "<USER_", "<PERSON>"]:
            print(f"  {balise:9}:", modifies["message_anon"].str.count(balise).sum())
        for avant, apres in modifies[["message", "message_anon"]].head(10).values:
            print(f"  AVANT : {avant}\n  APRÈS : {apres}\n")

        # Sauvegarde : on remplace la colonne d'origine par la version anonymisée
        df["message"] = df["message_anon"]
        sortie = chemin_sortie(chemin)
        df.drop(columns="message_anon").to_csv(sortie, index=False)
        print(f"  -> écrit : {sortie}")

    # Justification du filtrage : ce que spaCy seul aurait remplacé à tort
    print("\n=== Entités PERSON de spaCy REJETÉES (non confirmées par le dictionnaire)")
    print(f"  {sum(total_rejetees.values())} détections rejetées, top 25 :")
    for mot, n in total_rejetees.most_common(25):
        print(f"    {n:4}  {mot}")
