"""Backward-compat : imports déplacés vers hal_voice.domain + adapters.config_loader."""

from hal_voice.adapters.config_loader import load_config_from_env as _load_config_from_env
from hal_voice.domain.config import (
    DEFAULT_CHANNELS,
    DEFAULT_DTYPE,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_VOSK_MODEL_NAME,
    DEFAULT_VOSK_MODEL_PATH,
    DEFAULT_WAKE_WORD,
    MODELS_DIR,
    PROJECT_ROOT,
    Config,
)

if not hasattr(Config, "from_env"):
    Config.from_env = classmethod(lambda cls: _load_config_from_env())  # type: ignore[attr-defined]

__all__ = [
    "DEFAULT_CHANNELS",
    "DEFAULT_DTYPE",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_VOSK_MODEL_NAME",
    "DEFAULT_VOSK_MODEL_PATH",
    "DEFAULT_WAKE_WORD",
    "MODELS_DIR",
    "PROJECT_ROOT",
    "Config",
]
