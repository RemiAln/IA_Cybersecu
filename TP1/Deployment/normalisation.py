"""
TP2 - Étape 3 : DÉFENSE contre l'attaque d'évasion (obfuscation du texte)
=========================================================================

L'autre binôme nous attaque en déguisant les insultes pour qu'elles passent
le filtre : leetspeak (idi0t), espaces (i d i o t), homoglyphes (іdіot avec
des lettres cyrilliques), caractères invisibles. Le mot reste lisible pour
un humain, mais le modèle ne le reconnaît plus.

Idée de la défense : NETTOYER le texte AVANT de le donner au modèle, pour
annuler le déguisement. Le modèle revoit alors un texte normal, proche de
celui sur lequel il a été entraîné, et détecte à nouveau l'insulte.

-> Branché tout au début du traitement de la requête dans api.py (avant le
   prétraitement existant), sans toucher au modèle lui-même.

Ce fichier contient :
  1. la fonction `normaliser()`  -> la défense, importée dans l'API
  2. un petit test `python Deployment/normalisation.py` (depuis TP1/)
     qui prouve, sans l'API, que le nettoyage remet les insultes en clair.
"""

import re
import unicodedata

# Lettres qui se ressemblent à l'œil mais ne sont pas des lettres latines
# (cyrillique, grec). On les remet en alphabet normal.
HOMOGLYPHES = {
    "а": "a", "е": "e", "о": "o", "і": "i", "с": "c", "р": "p", "у": "y", "х": "x",  # cyrillique
    "ѕ": "s", "ԁ": "d", "ɡ": "g", "ν": "v", "ο": "o", "τ": "t",                      # grec/divers
}

# Correspondance leetspeak -> lettre. On reste PRUDENT : on ne "dé-leet" que
# dans les mots qui contiennent au moins une lettre (ex : "idi0t"), pour ne pas
# abîmer un vrai nombre comme "2026" ou "20h".
LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a"}

# Caractères invisibles (largeur nulle) utilisés pour couper un mot sans que
# ça se voie : espace de largeur nulle, (non-)liant, BOM.
INVISIBLES = ("​", "‌", "‍", "﻿")


def _supprimer_invisibles(texte):
    """Enlève les caractères de largeur nulle et les marques combinantes
    (accents ajoutés artificiellement pour casser les mots)."""
    sans_zw = "".join(c for c in texte if c not in INVISIBLES)
    # NFKD sépare les lettres de leurs accents ; on retire les accents "combinants"
    decompose = unicodedata.normalize("NFKD", sans_zw)
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _remplacer_homoglyphes(texte):
    return "".join(HOMOGLYPHES.get(c, c) for c in texte)


def _de_espacer(texte):
    """Recolle les mots écrits lettre par lettre : "i d i o t" -> "idiot".
    On ne recolle que les suites d'au moins 3 caractères seuls séparés par
    des espaces, pour ne pas fusionner de vrais mots courts. Les caractères
    leet comptent comme des lettres : "i d i 0 t" -> "idi0t" (puis _de_leet)."""
    car = r"(?:[^\W\d_]|[" + re.escape("".join(LEET)) + r"])"   # lettre ou caractère leet
    # suite de "car espace car espace ..." (au moins 3), délimitée par des espaces
    motif = re.compile(rf"(?<!\S)(?:{car}\s){{2,}}{car}(?!\S)", re.UNICODE)
    return motif.sub(lambda m: re.sub(r"\s", "", m.group(0)), texte)


def _de_leet(texte):
    """Remet les chiffres/symboles leet en lettres dans tout mot contenant AU
    MOINS une lettre : '1d10t' -> 'idiot', '$tupid' -> 'stupid', '4re' -> 'are'.
    Un token SANS aucune lettre est un vrai nombre ('2026', '20h') et reste intact.
    Contrepartie assumée : un mot bénin commençant par un chiffre-leet peut être
    modifié ('4pm' -> 'apm', '4u' -> 'au') ; sans gravité pour la modération."""
    def remplace(mot):
        if not re.search(r"[^\W\d_]", mot):   # aucune lettre -> vrai nombre, on laisse
            return mot
        return "".join(LEET.get(c, c) for c in mot)
    return re.sub(r"\S+", lambda m: remplace(m.group(0)), texte)


def normaliser(texte):
    """LA défense. Enchaîne les nettoyages dans le bon ordre et renvoie un
    texte 'démasqué', prêt à être donné au modèle."""
    texte = unicodedata.normalize("NFKC", texte)   # unifie les formes Unicode
    texte = _supprimer_invisibles(texte)           # vire invisibles + faux accents
    texte = _remplacer_homoglyphes(texte)          # cyrillique -> latin
    texte = _de_espacer(texte)                      # "i d i o t" -> "idiot"
    texte = _de_leet(texte)                         # "idi0t" -> "idiot"
    texte = re.sub(r"\s+", " ", texte).strip()      # espaces en trop
    return texte


# --------------------------------------------------------------------------
# Test rapide : prouve que le nettoyage annule les déguisements de l'attaque,
# sans avoir besoin de l'API. On réutilise les mêmes obfuscations qu'eux.
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    # La console Windows (cp1252) ne sait pas afficher le cyrillique : on force
    # l'UTF-8 pour la sortie, sinon le print des exemples déguisés planterait.
    sys.stdout.reconfigure(encoding="utf-8")

    exemples = [
        "You are a stupid idiot",         # clair (référence)
        "You are a stupid idi0t",         # leet
        "You are a stupid i d i o t",     # espaces
        "You are a stupid іdіot",         # homoglyphes (i cyrilliques)
        "You are a stupid idi​ot",   # caractère invisible
        "Y0u 4re a $tup1d i d i 0 t",     # combo
        "Rendez-vous à 3pm, c'est top",   # sain : NE DOIT PAS être cassé
    ]
    print(f"{'ENTRÉE (déguisée)':<34} -> SORTIE (nettoyée)")
    print("-" * 70)
    for e in exemples:
        print(f"{e!r:<34} -> {normaliser(e)}")
