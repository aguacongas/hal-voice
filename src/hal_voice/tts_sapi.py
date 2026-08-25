"""
tts_sapi — Text-to-Speech via SAPI 5 (Windows natif).

Utilise le composant COM `SAPI.SpVoice` via `win32com.client`.
Zéro installation, voix Microsoft déjà présentes sur Windows 11.

Voix par défaut : on cherche la 1ère voix FR (locale 0x040C) ;
fallback : 1ère voix disponible.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import win32com.client

log = logging.getLogger(__name__)

FRENCH_LANG_ID = 0x040C  # fr-FR


def _lang_id_to_int(value: str | int) -> int:
    """SAPI renvoie l'attribut Language comme string hexadécimale ('40C')."""
    if isinstance(value, str):
        return int(value, 16)
    return int(value)


class TTS:
    """Wrapper TTS basé sur SAPI 5 (Windows)."""

    def __init__(self, voice_name: Optional[str] = None) -> None:
        self._speaker = win32com.client.Dispatch("SAPI.SpVoice")
        self._voices = self._speaker.GetVoices()
        self._set_voice(voice_name)

    # ---------- API publique ----------

    def list_voices(self) -> list[dict]:
        """Renvoie la liste des voix disponibles avec description + langue."""
        result: list[dict] = []
        for i in range(self._voices.Count):
            v = self._voices.Item(i)
            result.append({
                "index": i,
                "description": v.GetDescription(),
                "language_id": _lang_id_to_int(v.GetAttribute("Language")),
            })
        return result

    def speak(self, text: str, blocking: bool = True) -> None:
        """Prononce `text`. Bloquant par défaut."""
        if not text or not text.strip():
            return
        flags = 0 if blocking else 1  # SPF_ASYNC = 1
        self._speaker.Speak(text, flags)

    def stop(self) -> None:
        """Interrompt la parole en cours."""
        # SPF_PURGEBEFORESPEAK = 2
        self._speaker.Speak("", 2)

    @property
    def voice_name(self) -> str:
        """Description de la voix actuellement sélectionnée."""
        return self._speaker.Voice.GetDescription()

    # ---------- Privé ----------

    def _set_voice(self, voice_name: Optional[str]) -> None:
        target_index: Optional[int] = None

        # 1. Nom demandé explicitement
        if voice_name:
            for i in range(self._voices.Count):
                v = self._voices.Item(i)
                if voice_name.lower() in v.GetDescription().lower():
                    target_index = i
                    break
            if target_index is None:
                log.warning(
                    "Voix %r introuvable, fallback sur la 1ere voix FR.",
                    voice_name,
                )

        # 2. Fallback : 1ere voix FR
        if target_index is None:
            target_index = self._find_first_french()

        # 3. Dernier fallback : 1ere voix dispo
        if target_index is None:
            target_index = 0

        self._speaker.Voice = self._voices.Item(target_index)
        log.info("Voix TTS selectionnee : %s", self.voice_name)

    def _find_first_french(self) -> Optional[int]:
        for i in range(self._voices.Count):
            v = self._voices.Item(i)
            if _lang_id_to_int(v.GetAttribute("Language")) == FRENCH_LANG_ID:
                return i
        return None


__all__ = ["TTS"]
