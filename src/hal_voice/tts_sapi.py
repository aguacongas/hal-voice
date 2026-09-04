"""Backward-compat : imports déplacés vers hal_voice.adapters.tts."""

from hal_voice.adapters.tts import FRENCH_LANG_ID, TTS, _lang_id_to_int

__all__ = ["FRENCH_LANG_ID", "TTS", "_lang_id_to_int"]
