"""
config — chemins et paramètres globaux.

Tout est centralisé ici pour qu'on ne hardcode rien dans les modules.
Lisible depuis l'environnement (HAL_VOICE_MODEL_PATH, HAL_VOICE_SAMPLE_RATE...).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

# Modèle Vosk par défaut (FR, small)
DEFAULT_VOSK_MODEL_NAME = "vosk-model-small-fr-0.22"
DEFAULT_VOSK_MODEL_PATH = MODELS_DIR / DEFAULT_VOSK_MODEL_NAME

# Audio
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
DEFAULT_DTYPE = "int16"

# Voix TTS
#   Windows SAPI 5 : hint "fr" → 1ère voix FR trouvée
#   Linux pyttsx3   : id eSpeak FR → voix française eSpeak
DEFAULT_TTS_VOICE_NAME_HINT = "fr"

# Wake word (placeholder v0.3)
DEFAULT_WAKE_WORD = "hal"


@dataclass(frozen=True)
class Config:
    """Snapshot immutable des paramètres runtime."""

    vosk_model_path: Path
    sample_rate: int
    channels: int
    dtype: str
    wake_word: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            vosk_model_path=Path(
                os.environ.get("HAL_VOICE_MODEL_PATH", str(DEFAULT_VOSK_MODEL_PATH))
            ),
            sample_rate=int(os.environ.get("HAL_VOICE_SAMPLE_RATE", DEFAULT_SAMPLE_RATE)),
            channels=int(os.environ.get("HAL_VOICE_CHANNELS", DEFAULT_CHANNELS)),
            dtype=os.environ.get("HAL_VOICE_DTYPE", DEFAULT_DTYPE),
            wake_word=os.environ.get("HAL_VOICE_WAKE_WORD", DEFAULT_WAKE_WORD),
        )
