"""Backward-compat : imports déplacés vers hal_voice.adapters.stt_vosk."""

from hal_voice.adapters.stt_vosk import STT
from hal_voice.domain.config import DEFAULT_SAMPLE_RATE

__all__ = ["DEFAULT_SAMPLE_RATE", "STT"]
