"""
config — Chemins et paramètres globaux de hal-voice.

Tout est centralisé ici pour qu'on ne hardcode rien dans les modules.
Les paramètres sont lisibles depuis l'environnement pour permettre
la configuration sans modifier le code.

Variables d'environnement supportées :
    HAL_VOICE_MODEL_PATH  → chemin vers le modèle Vosk (défaut: models/vosk-model-small-fr-0.22)
    HAL_VOICE_SAMPLE_RATE → fréquence d'échantillonnage (défaut: 16000)
    HAL_VOICE_CHANNELS    → nombre de canaux (défaut: 1)
    HAL_VOICE_DTYPE       → type de données audio (défaut: int16)
    HAL_VOICE_WAKE_WORD   → mot d'activation (défaut: hal)

Architecture :
    - PROJECT_ROOT : racine du projet (parent de src/)
    - MODELS_DIR   : dossier contenant les modèles Vosk
    - Config       : dataclass immutable des paramètres runtime
      → Config.from_env() crée une Config depuis les variables d'env
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Racine du projet : remonte de src/hal_voice/ vers la racine
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Dossier des modèles Vosk (gitignored)
MODELS_DIR = PROJECT_ROOT / "models"

# ── Modèle Vosk par défaut ────────────────────────────────────────────
# Vosk small FR : ~40 Mo, précis pour le français, léger en RAM
DEFAULT_VOSK_MODEL_NAME = "vosk-model-small-fr-0.22"
DEFAULT_VOSK_MODEL_PATH = MODELS_DIR / DEFAULT_VOSK_MODEL_NAME

# ── Paramètres audio par défaut ───────────────────────────────────────
# 16 kHz : standard pour la STT (Vosk, Whisper, etc.)
DEFAULT_SAMPLE_RATE = 16_000
# Mono : un seul canal, suffisant pour la reconnaissance vocale
DEFAULT_CHANNELS = 1
# int16 : 16 bits signés, format natif de Vosk
DEFAULT_DTYPE = "int16"

# ── Voix TTS par défaut ───────────────────────────────────────────────
# Windows SAPI 5 : hint "fr" → cherche la première voix FR trouvée
# Linux pyttsx3   : id eSpeak FR → voix française eSpeak
DEFAULT_TTS_VOICE_NAME_HINT = "fr"

# ── Wake word (mot d'activation) ──────────────────────────────────────
# Placeholder pour la v0.3 — pas encore utilisé dans la boucle principale
DEFAULT_WAKE_WORD = "hal"


@dataclass(frozen=True)
class Config:
    """Snapshot immutable des paramètres runtime.

    ``frozen=True`` empêche la modification accidentelle après création.
    Utilisé comme un namespace de configuration : tous les modules
    reçoivent une Config et lisent ses attributs.
    """

    vosk_model_path: Path
    sample_rate: int
    channels: int
    dtype: str
    wake_word: str

    @classmethod
    def from_env(cls) -> Config:
        """Crée une Config depuis les variables d'environnement.

        Chaque champ a une valeur par défaut utilisée si la variable
        d'environnement n'est pas définie. Le cast vers le bon type
        se fait ici pour éviter les erreurs plus tard.
        """
        return cls(
            vosk_model_path=Path(
                os.environ.get("HAL_VOICE_MODEL_PATH", str(DEFAULT_VOSK_MODEL_PATH))
            ),
            sample_rate=int(os.environ.get("HAL_VOICE_SAMPLE_RATE", DEFAULT_SAMPLE_RATE)),
            channels=int(os.environ.get("HAL_VOICE_CHANNELS", DEFAULT_CHANNELS)),
            dtype=os.environ.get("HAL_VOICE_DTYPE", DEFAULT_DTYPE),
            wake_word=os.environ.get("HAL_VOICE_WAKE_WORD", DEFAULT_WAKE_WORD),
        )
