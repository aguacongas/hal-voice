"""
tts — Text-to-Speech multi-plateforme.

Windows : SAPI 5 via win32com (zéro installation).
Linux/WSL : pyttsx3 + eSpeak-ng.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

# Import conditionnel de win32com (Windows only)
_win32com = None
if sys.platform == "win32":
    try:
        import win32com.client as _win32com  # type: ignore[no-redef]
    except ImportError:
        log.warning("win32com non disponible. TTS SAPI 5 désactivé.")

FRENCH_LANG_ID = 0x040C  # fr-FR


def _lang_id_to_int(value: str | int) -> int:
    """SAPI renvoie l'attribut Language comme string hexadécimale ('40C')."""
    if isinstance(value, str):
        return int(value, 16)
    return int(value)


class TTS:
    """Wrapper TTS multi-plateforme. SAPI 5 sur Windows, pyttsx3 sur Linux."""

    def __init__(self, voice_name: str | None = None) -> None:
        if sys.platform == "win32":
            self._backend = _SapiBackend(voice_name)
        else:
            self._backend = _Pyttsx3Backend(voice_name)

    def list_voices(self) -> list[dict]:
        """Renvoie la liste des voix disponibles avec description + langue."""
        return self._backend.list_voices()

    def speak(self, text: str, blocking: bool = True) -> None:
        """Prononce ``text``. Bloquant par défaut."""
        if not text or not text.strip():
            return
        self._backend.speak(text, blocking)

    def stop(self) -> None:
        """Interrompt la parole en cours."""
        self._backend.stop()

    @property
    def voice_name(self) -> str:
        """Description de la voix actuellement sélectionnée."""
        return self._backend.voice_name


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class _SapiBackend:
    """Windows SAPI 5 via COM."""

    def __init__(self, voice_name: str | None = None) -> None:
        self._speaker = _win32com.Dispatch("SAPI.SpVoice")
        self._voices = self._speaker.GetVoices()
        self._set_voice(voice_name)

    def list_voices(self) -> list[dict]:
        result: list[dict] = []
        for i in range(self._voices.Count):
            v = self._voices.Item(i)
            result.append({
                "index": i,
                "description": v.GetDescription(),
                "language_id": _lang_id_to_int(v.GetAttribute("Language")),
            })
        return result

    def speak(self, text: str, blocking: bool) -> None:
        flags = 0 if blocking else 1  # SPF_ASYNC = 1
        self._speaker.Speak(text, flags)

    def stop(self) -> None:
        self._speaker.Speak("", 2)  # SPF_PURGEBEFORESPEAK

    @property
    def voice_name(self) -> str:
        return self._speaker.Voice.GetDescription()

    def _set_voice(self, voice_name: str | None) -> None:
        target_index: int | None = None

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

        if target_index is None:
            target_index = self._find_first_french()

        if target_index is None:
            target_index = 0

        self._speaker.Voice = self._voices.Item(target_index)
        log.info("Voix TTS selectionnee : %s", self.voice_name)

    def _find_first_french(self) -> int | None:
        for i in range(self._voices.Count):
            v = self._voices.Item(i)
            if _lang_id_to_int(v.GetAttribute("Language")) == FRENCH_LANG_ID:
                return i
        return None


class _Pyttsx3Backend:
    """pyttsx3 + eSpeak pour Linux / WSL."""

    def __init__(self, voice_name: str | None = None) -> None:
        import pyttsx3

        self._engine = pyttsx3.init()
        self._voice_name = ""
        self._set_voice(voice_name)

    def list_voices(self) -> list[dict]:
        result: list[dict] = []
        for i, v in enumerate(self._engine.getProperty("voices")):
            result.append({
                "index": i,
                "description": v.name,
                "language_id": 0,
            })
        return result

    def speak(self, text: str, blocking: bool) -> None:
        self._engine.say(text)
        if blocking:
            self._engine.runAndWait()

    def stop(self) -> None:
        self._engine.stop()

    @property
    def voice_name(self) -> str:
        return self._voice_name

    def _set_voice(self, voice_name: str | None) -> None:
        voices = self._engine.getProperty("voices")
        target = None

        if voice_name:
            for v in voices:
                if voice_name.lower() in v.name.lower():
                    target = v
                    break
            if target is None:
                log.warning(
                    "Voix %r introuvable, fallback sur la 1ere voix FR.",
                    voice_name,
                )

        if target is None:
            for v in voices:
                if "fr" in v.id.lower():
                    target = v
                    break

        if target is None and voices:
            target = voices[0]

        if target:
            self._engine.setProperty("voice", target.id)
            self._voice_name = target.name
            log.info("Voix TTS selectionnee : %s", self._voice_name)


__all__ = ["TTS"]
