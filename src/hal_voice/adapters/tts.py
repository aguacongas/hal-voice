"""
adapters.tts — Text-to-Speech multi-plateforme (implémentation concrète).

Windows : SAPI 5 via win32com (zéro installation, voix système).
Linux/WSL : pyttsx3 + eSpeak-ng (nécessite ``apt install espeak-ng``).

Vérifie le protocole domain.protocols.ITTS.

Architecture :
    TTS est une facade qui délègue au bon backend selon la plateforme.
    - _SapiBackend : Windows SAPI 5 via COM (win32com.client)
    - _Pyttsx3Backend : pyttsx3 (wrapper multi-plateforme, utilise eSpeak sous Linux)

Sélection de la voix :
    - Si voice_name est fourni, on cherche la voix correspondante
    - Sinon, on prend la première voix française disponible
    - Fallback : la première voix du système

Flags SAPI 5 :
    - SPF_ASYNC (1) : lecture asynchrone (non bloquant)
    - SPF_PURGEBEFORESPEAK (2) : purge la file avant de parler
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

# Identifiant de langue français pour SAPI 5 (0x040C = 1036)
FRENCH_LANG_ID = 0x040C


def _lang_id_to_int(value: str | int) -> int:
    """Convertit un identifiant de langue SAPI en entier.

    SAPI renvoie l'attribut Language comme string hexadécimale ('40C')
    ou parfois comme un entier. pyttsx3 peut retourner des tags BCP 47
    (ex: 'gmw/af') qui ne sont pas hex → on retourne 0 dans ce cas.
    """
    if isinstance(value, int):
        return value
    try:
        return int(value, 16)
    except (ValueError, TypeError):
        return 0


def _select_voice(setter, voices, voice_name: str | None, get_desc, get_attr, set_prop) -> str:
    """Logique commune de sélection de voix.

    1. Si voice_name fourni → cherche par nom
    2. Sinon → première voix FR
    3. Fallback → première voix du système
    """
    target = None
    if voice_name:
        for v in voices:
            if voice_name.lower() in get_desc(v).lower():
                target = v
                break
        if target is None:
            log.warning("Voix %r introuvable, fallback sur la 1ere voix FR.", voice_name)

    if target is None:
        for v in voices:
            lang = get_attr(v)
            if _lang_id_to_int(lang) == FRENCH_LANG_ID:
                target = v
                break

    if target is None and voices:
        target = voices[0]

    if target is not None:
        set_prop(target)
        name = get_desc(target)
        log.info("Voix TTS selectionnee : %s", name)
        return name
    return ""


class TTS:
    """Wrapper TTS multi-plateforme.

    SAPI 5 sur Windows, pyttsx3+eSpeak sur Linux/WSL.
    Le backend est choisi automatiquement selon ``sys.platform``.
    """

    def __init__(self, voice_name: str | None = None) -> None:
        if sys.platform == "win32":
            self._backend = _SapiBackend(voice_name)
        else:
            self._backend = _Pyttsx3Backend(voice_name)

    def list_voices(self) -> list[dict]:
        """Renvoie la liste des voix disponibles."""
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


class _SapiBackend:
    """Windows SAPI 5 via COM."""

    def __init__(self, voice_name: str | None = None) -> None:
        self._speaker = _win32com.Dispatch("SAPI.SpVoice")
        self._voices = self._speaker.GetVoices()
        self._voice_name = _select_voice(
            self._speaker,
            range(self._voices.Count),
            voice_name,
            lambda i: self._voices.Item(i).GetDescription(),
            lambda i: self._voices.Item(i).GetAttribute("Language"),
            lambda v: setattr(self._speaker, "Voice", v),
        )

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
        flags = 0 if blocking else 1
        self._speaker.Speak(text, flags)

    def stop(self) -> None:
        self._speaker.Speak("", 2)

    @property
    def voice_name(self) -> str:
        return self._voice_name


class _Pyttsx3Backend:
    """pyttsx3 + eSpeak pour Linux / WSL."""

    def __init__(self, voice_name: str | None = None) -> None:
        import pyttsx3

        self._engine = pyttsx3.init()
        self._voice_name = ""
        voices = self._engine.getProperty("voices")
        self._voice_name = _select_voice(
            self._engine,
            voices,
            voice_name,
            lambda v: v.name,
            lambda v: v.id,
            lambda v: self._engine.setProperty("voice", v.id),
        )

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
