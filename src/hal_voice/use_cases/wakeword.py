"""
use_cases.wakeword — Détection du mot d'activation ("hal") + VAD adaptatif.

Use cases purs (aucune dépendance aux adapters matériels).
Deux responsabilités complémentaires pour le "mode veille" de v0.8.0 :

    1. ``WakeWordDetector`` : dit si un texte transcrit contient le
       mot d'activation, et peut le retirer pour ne garder que la suite.

    2. ``AdaptiveVoiceActivity`` (VAD) : estime en continu le plancher
       de bruit ambiant et signale la présence de parole. Sert à ne
       lancer le STT que quand on parle réellement (écoute basse
       consommation), au lieu de transcrire en boucle.

Exemples :
    >>> WakeWordDetector("hal").matches("salut hal je t'ecoute")
    True
    >>> WakeWordDetector("hal").strip_wake_word("hal ecoute ceci") == "ecoute ceci"
    True
"""

from __future__ import annotations


class WakeWordDetector:
    """Détecte le mot d'activation dans un texte transcrit.

    Le wake word peut être un mot simple ("hal") ou une phrase
    ("ok hal"). La détection est insensible à la casse et ignore la
    ponctuation autour des mots.
    """

    def __init__(self, wake_word: str = "hal") -> None:
        w = wake_word.strip().lower()
        self._wake_word = w
        self._tokens = {t for t in w.split() if t}

    @property
    def wake_word(self) -> str:
        """Le mot d'activation (forme normalisée)."""
        return self._wake_word

    @staticmethod
    def _bare(token: str) -> str:
        """Retire la ponctuation qui entoure un mot."""
        return token.strip(".,!?;:'\"()[]{}—–-")

    def matches(self, text: str) -> bool:
        """True si ``text`` contient tous les mots du mot d'activation.

        Pour un wake word multi-mots ("ok hal"), tous les tokens doivent
        être présents dans la transcription (ordre libre).
        """
        if not text or not self._tokens:
            return False
        tokens = {self._bare(t) for t in text.lower().split()}
        return self._tokens.issubset(tokens)

    def strip_wake_word(self, text: str) -> str:
        """Retire le mot d'activation et retourne le reste du texte.

        Utile pour isoler la commande qui suit le wake word.
        """
        if not text:
            return ""
        kept = [
            t for t in text.split()
            if self._bare(t.lower()) not in self._tokens
        ]
        return " ".join(kept).strip()


class AdaptiveVoiceActivity:
    """Détection d'activité vocale fondée sur un plancher de bruit adaptatif.

    Au fil des lectures, on maintient une estimation du bruit de fond
    (moyenne mobile exponentielle). Un échantillon est considéré comme
    "parole" si son amplitude dépasse ``noise_floor * factor``.

    Quand rien ne dépasse le seuil, le plancher glisse vers le niveau
    ambiant courant (il s'adapte aux changements de bruit de fond).

    Attributes:
        factor: multiplicateur du plancher pour former le seuil de parole.
        init_floor: plancher initial (avant toute mesure).
        alpha: taux d'apprentissage de la moyenne mobile (0..1).
    """

    def __init__(
        self,
        factor: float = 3.0,
        init_floor: float = 200.0,
        alpha: float = 0.05,
    ) -> None:
        self._factor = float(factor)
        self._alpha = float(alpha)
        self._noise_floor = float(init_floor)

    @property
    def noise_floor(self) -> float:
        """Niveau de bruit de fond actuellement estimé."""
        return self._noise_floor

    @property
    def threshold(self) -> float:
        """Seuil de parole courant (``noise_floor * factor``)."""
        return self._noise_floor * self._factor

    def update(self, amplitude: float) -> bool:
        """Met à jour le plancher et retourne True si ``amplitude`` = parole.

        - Si l'amplitude dépasse le seuil → parole (True), plancher inchangé.
        - Sinon → silence (False), le plancher glisse vers l'amplitude courante.
        """
        amp = float(amplitude)
        if amp >= self.threshold:
            return True
        self._noise_floor = (
            (1.0 - self._alpha) * self._noise_floor + self._alpha * amp
        )
        return False
