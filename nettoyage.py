"""
TP1 - Étape 2 : nettoyage des textes avant l'entraînement

Deux niveaux de nettoyage, selon le modèle :
  - nettoyer_lstm()        : nettoyage fort (minuscules, ponctuation retirée),
                             car le LSTM apprend sur un vocabulaire de mots entiers.
  - nettoyer_transformer() : nettoyage léger, car BERT et Laya ont leur propre
                             tokenizer et tirent du sens des majuscules et de la
                             ponctuation ("STOP!!!" n'est pas "stop").
"""

import html
import re

import emoji

# Balises posées à l'étape 1. Le code d'un pseudo (<USER_3f2a9c1e>) n'apporte
# rien au modèle : on garde seulement l'information "un joueur est visé".
USER_RE = re.compile(r"<USER_[0-9a-f]{8}>")

# Dans le fichier d'origine, les caractères accentués (et sans doute les emojis)
# sont devenus "??" : "d??gage". On retire ces trous à l'intérieur des mots.
TROU_ENCODAGE_RE = re.compile(r"(?<=\w)\?{2,}(?=\w)")

# "noooooob", "!!!!!!!" -> 3 répétitions maximum
REPETITION_RE = re.compile(r"(.)\1{3,}")

# Émoticônes fréquentes dans le chat : elles portent une intention
# (moquerie, colère), on les transforme en mots pour le LSTM.
EMOTICONES = {
    ":)": " smiley ", ":-)": " smiley ", ":D": " rire ", "xD": " rire ", "XD": " rire ",
    ":(": " triste ", ":-(": " triste ", ":P": " langue ", ":p": " langue ",
}


def nettoyage_commun(texte: str) -> str:
    """Corrections appliquées quel que soit le modèle."""
    texte = html.unescape(str(texte))                 # "&gt;" -> ">"
    texte = USER_RE.sub("<USER>", texte)
    texte = TROU_ENCODAGE_RE.sub("", texte)
    # Les emojis sont convertis en texte plutôt que supprimés : "🖕" est une
    # insulte. Aucun dans GameTox, mais l'API en recevra.
    texte = emoji.demojize(texte, delimiters=(" ", " "))
    texte = REPETITION_RE.sub(r"\1\1\1", texte)
    return re.sub(r"\s+", " ", texte).strip()


def nettoyer_transformer(texte: str) -> str:
    """Nettoyage léger pour BERT et Laya : casse et ponctuation conservées."""
    return nettoyage_commun(texte)


def nettoyer_lstm(texte: str) -> str:
    """Nettoyage fort pour le LSTM : un vocabulaire petit et régulier."""
    texte = nettoyage_commun(texte)
    for emoticone, mot in EMOTICONES.items():
        texte = texte.replace(emoticone, mot)
    texte = texte.lower()
    # Les balises deviennent des mots simples : <person> -> person_tag
    texte = re.sub(r"<(person|user|url|email|ip|phone)>", r" \1_tag ", texte)
    # On garde "!" et "?" (l'agressivité passe souvent par là) et "*" (insultes
    # censurées : "f***"). Le reste de la ponctuation est retiré.
    texte = re.sub(r"([!?*])", r" \1 ", texte)
    texte = re.sub(r"[^\w\s!?*]", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


if __name__ == "__main__":
    # Démonstration rapide avant / après
    exemples = [
        "BattleGreen (Skorpion G), T'es tellement gros que tu bloque mon tir d??gage!",
        "<USER_775a2a10> (Kunze Panzer), you're blocking my line of fire!!!!!!",
        "noooooob team :D &gt;=O",
        "I will **** claus ******",
        "gg 🖕",
    ]
    for e in exemples:
        print(f"AVANT       : {e}")
        print(f"TRANSFORMER : {nettoyer_transformer(e)}")
        print(f"LSTM        : {nettoyer_lstm(e)}\n")
