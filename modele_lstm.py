from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import f1_score

from evaluation import (GRAINE, NB_NOTES, Chrono, charger_donnees, evaluer,
                        poids_classes)

# Les messages sont déjà nettoyés par nettoyage.py (fichiers *_clean.csv chargés
# par charger_donnees) : aucun nettoyage supplémentaire ici.

torch.manual_seed(GRAINE)
np.random.seed(GRAINE)
APPAREIL = "cuda" if torch.cuda.is_available() else "cpu"

# Hyperparamètres (choisis petits : messages de 2 mots en médiane, 30 au maximum)
LONGUEUR_MAX = 30
FREQ_MIN = 2            # un mot vu une seule fois n'entre pas dans le vocabulaire
DIM_EMBEDDING = 100
DIM_CACHEE = 64
TAILLE_LOT = 128
EPOCHS_MAX = 10
PATIENCE = 2            # arrêt si la validation ne progresse plus pendant 2 epochs


# ---------------------------------------------------------------------------
# Texte -> suite de numéros de mots
# ---------------------------------------------------------------------------
PAD, INCONNU = 0, 1


def construire_vocabulaire(textes):
    compte = Counter(mot for t in textes for mot in t.split())
    mots = [m for m, n in compte.items() if n >= FREQ_MIN]
    return {m: i + 2 for i, m in enumerate(sorted(mots))}   # 0 et 1 sont réservés


def encoder(textes, vocab) -> torch.Tensor:
    lignes = np.full((len(textes), LONGUEUR_MAX), PAD, dtype=np.int64)
    for i, t in enumerate(textes):
        ids = [vocab.get(m, INCONNU) for m in t.split()][:LONGUEUR_MAX]
        lignes[i, :len(ids)] = ids or [INCONNU]
    return torch.from_numpy(lignes)


# ---------------------------------------------------------------------------
# Le réseau
# ---------------------------------------------------------------------------
class ClassifieurLSTM(nn.Module):
    def __init__(self, taille_vocab):
        super().__init__()
        self.embedding = nn.Embedding(taille_vocab, DIM_EMBEDDING, padding_idx=PAD)
        # bidirectionnel : lit le message dans les deux sens
        self.lstm = nn.LSTM(DIM_EMBEDDING, DIM_CACHEE, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(0.3)
        self.sortie = nn.Linear(2 * DIM_CACHEE, NB_NOTES)

    def forward(self, x):
        etats, _ = self.lstm(self.embedding(x))
        # max-pooling sur les mots (hors padding) : on garde le signal le plus
        # fort du message, où que soit placée l'insulte
        masque = (x != PAD).unsqueeze(-1)
        etats = etats.masked_fill(~masque, -1e4)
        return self.sortie(self.dropout(etats.max(dim=1).values))


def predire(modele, X) -> np.ndarray:
    """Probabilités des 6 notes pour chaque message."""
    modele.eval()
    sorties = []
    with torch.no_grad():
        for i in range(0, len(X), 512):
            sorties.append(torch.softmax(modele(X[i:i + 512].to(APPAREIL)), dim=1).cpu())
    return torch.cat(sorties).numpy()


def f1_toxique(labels, probas):
    return f1_score(np.asarray(labels) >= 1, (1 - probas[:, 0]) >= 0.5)


# ---------------------------------------------------------------------------
# Entraînement
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    train, valid, test = charger_donnees()
    textes = {nom: df["message"].tolist()
              for nom, df in [("train", train), ("valid", valid), ("test", test)]}

    vocab = construire_vocabulaire(textes["train"])
    print(f"Vocabulaire : {len(vocab)} mots (appareil : {APPAREIL})")
    X = {nom: encoder(t, vocab) for nom, t in textes.items()}
    y_train = torch.tensor(train["label"].values)

    modele = ClassifieurLSTM(len(vocab) + 2).to(APPAREIL)
    perte = nn.CrossEntropyLoss(
        weight=torch.tensor(poids_classes(train["label"].values), dtype=torch.float32).to(APPAREIL))
    optimiseur = torch.optim.Adam(modele.parameters(), lr=2e-3)

    meilleur_f1, sans_progres, meilleur_etat = -1, 0, None
    for epoch in range(1, EPOCHS_MAX + 1):
        modele.train()
        ordre = torch.randperm(len(y_train))
        for i in range(0, len(ordre), TAILLE_LOT):
            lot = ordre[i:i + TAILLE_LOT]
            optimiseur.zero_grad()
            l = perte(modele(X["train"][lot].to(APPAREIL)), y_train[lot].to(APPAREIL))
            l.backward()
            optimiseur.step()

        f1_valid = f1_toxique(valid["label"], predire(modele, X["valid"]))
        print(f"epoch {epoch} : F1 validation = {f1_valid:.4f}")
        # On garde le meilleur epoch, pas le dernier (évite le surapprentissage)
        if f1_valid > meilleur_f1:
            meilleur_f1, sans_progres = f1_valid, 0
            meilleur_etat = {k: v.clone() for k, v in modele.state_dict().items()}
        else:
            sans_progres += 1
            if sans_progres >= PATIENCE:
                print("arrêt : plus de progrès sur la validation")
                break

    modele.load_state_dict(meilleur_etat)
    Path("modeles").mkdir(exist_ok=True)
    torch.save({"etat": meilleur_etat, "vocab": vocab}, "modeles/lstm.pt")

    # Évaluation sur le test ; le chrono inclut l'encodage des textes, comme dans l'API
    with Chrono() as c:
        X_test = encoder(test["message"].tolist(), vocab)
        probas = predire(modele, X_test)
    evaluer("lstm", test["label"], probas, c.duree, APPAREIL)
