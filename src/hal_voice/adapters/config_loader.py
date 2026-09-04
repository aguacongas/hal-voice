"""
adapters.config_loader — Chargement de la Config depuis l'environnement.

Adapter : dépendance externe = os.environ.
Le domain.config.Config est une entité pure ; ce module sait
comment la remplir depuis les variables d'environnement.

Variables supportées :
    HAL_VOICE_MODEL_PATH, HAL_VOICE_SAMPLE_RATE, HAL_VOICE_CHANNELS,
    HAL_VOICE_DTYPE, HAL_VOICE_WAKE_WORD, HAL_VOICE_SILENT

Le flag silencieux peut aussi venir d'un argument CLI ``--silent``
(transmis via ``sys.argv``) pour désactiver la synthèse vocale.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hal_voice.domain.config import (
    DEFAULT_CHANNELS,
    DEFAULT_DTYPE,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_VOSK_MODEL_PATH,
    DEFAULT_WAKE_WORD,
    Config,
)


def _env_bool(name: str) -> bool:
    """Interprète une variable d'environnement comme booléen.

    Valeurs vraies : 1, true, yes, on (insensible à la casse).
    Tout le reste (vide, 0, false, absent) → False.
    """
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_config_from_env() -> Config:
    """Crée une Config depuis les variables d'environnement.

    Chaque champ a une valeur par défaut utilisée si la variable
    d'environnement n'est pas définie.
    """
    return Config(
        vosk_model_path=Path(
            os.environ.get("HAL_VOICE_MODEL_PATH", str(DEFAULT_VOSK_MODEL_PATH))
        ),
        sample_rate=int(os.environ.get("HAL_VOICE_SAMPLE_RATE", DEFAULT_SAMPLE_RATE)),
        channels=int(os.environ.get("HAL_VOICE_CHANNELS", DEFAULT_CHANNELS)),
        dtype=os.environ.get("HAL_VOICE_DTYPE", DEFAULT_DTYPE),
        wake_word=os.environ.get("HAL_VOICE_WAKE_WORD", DEFAULT_WAKE_WORD),
        silent=_env_bool("HAL_VOICE_SILENT") or "--silent" in sys.argv,
    )
