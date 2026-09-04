"""
tts — Text-to-Speech multi-plateforme.

Windows : SAPI 5 via win32com (zéro installation, voix système).
Linux/WSL : pyttsx3 + eSpeak-ng (nécessite ``apt install espeak-ng``).

Architecture :
    TTS est une facade qui délègue au bon backend selon la plateforme.
    - _SapiBackend : Windows SAPI 5 via COM (win32com.client)
    - _Pyttsx3Backend : pyttsx3 (wrapper multi-plateforme, utilise eSpeak sous Linux)

    L'utilisateur appelle TTS.speak(), TTS.stop(), TTS.list_voices().
    Le backend est choisi automatiquement à l'init.

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
# _win32com sera win32com.client sur Windows, None sur Linux
_win32com = None
if sys.platform == "win32":
    try:
        import win32com.client as _win32com  # type: ignore[no-redef]
    except ImportError:
        log.warning("win32com non disponible. TTS SAPI 5 désactivé.")

# Identifiant de langue français pour SAPI 5 (0x040C = 1036)
FRENCH_LANG_ID = 0x040C  # fr-FR


def _lang_id_to_int(value: str | int) -> int:
    """Convertit un identifiant de langue SAPI en entier.

    SAPI renvoie l'attribut Language comme string hexadécimale ('40C')
    ou parfois comme un entier. Cette fonction normalise les deux cas.
    """
    if isinstance(value, str):
        return int(value, 16)
    return int(value)


class TTS:
    """Wrapper TTS multi-plateforme.

    SAPI 5 sur Windows, pyttsx3+eSpeak sur Linux/WSL.
    Le backend est choisi automatiquement selon ``sys.platform``.
    """

    def __init__(self, voice_name: str | None = None) -> None:
        # Choix du backend selon la plateforme
        if sys.platform == "win32":
            self._backend = _SapiBackend(voice_name)
        else:
            self._backend = _Pyttsx3Backend(voice_name)

    def list_voices(self) -> list[dict]:
        """Renvoie la liste des voix disponibles avec description + langue."""
        return self._backend.list_voices()

    def speak(self, text: str, blocking: bool = True) -> None:
        """Prononce ``text``. Bloquant par défaut.

        Args:
            text: Texte à prononcer (peut contenir plusieurs phrases)
            blocking: Si True, attend la fin de la synthèse avant de retourner
        """
        if not text or not text.strip():
            return
        self._backend.speak(text, blocking)

    def stop(self) -> None:
        """Interrompt la parole en cours.

        Sur SAPI 5, utilise SPF_PURGEBEFORESPEAK pour vider la file.
        Sur pyttsx3, appelle engine.stop().
        """
        self._backend.stop()

    @property
    def voice_name(self) -> str:
        """Description de la voix actuellement sélectionnée."""
        return self._backend.voice_name


# ══════════════════════════════════════════════════════════════════════
# Backends
# ══════════════════════════════════════════════════════════════════════


class _SapiBackend:
    """Windows SAPI 5 via COM.

    Utilise win32com.client pour interagir avec l'API Speech de Windows.
    Zéro dépendance externe — SAPI 5 est installé par défaut sur Windows.

    Fonctionnement :
        1. Crée un objet SpVoice via COM
        2. Liste les voix disponibles
        3. Sélectionne la première voix française
        4. speak() appelle SpVoice.Speak(text, flags)
    """

    def __init__(self, voice_name: str | None = None) -> None:
        # Crée l'objet SAPI SpVoice via COM
        self._speaker = _win32com.Dispatch("SAPI.SpVoice")
        # Récupère la collection de voix disponibles
        self._voices = self._speaker.GetVoices()
        # Sélectionne la voix (par nom ou première FR)
        self._set_voice(voice_name)

    def list_voices(self) -> list[dict]:
        """Liste toutes les voix SAPI avec description et langue."""
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
        """Prononce le texte via SAPI.

        flags=0 : synchro (bloquant)
        flags=1 : asynchrone (SPF_ASYNC)
        """
        flags = 0 if blocking else 1  # SPF_ASYNC = 1
        self._speaker.Speak(text, flags)

    def stop(self) -> None:
        """Purge la file de synthèse et arrête la parole.

        SPF_PURGEBEFORESPEAK (2) vide la file avant de parler.
        En passant un texte vide avec ce flag, on arrête tout.
        """
        self._speaker.Speak("", 2)  # SPF_PURGEBEFORESPEAK

    @property
    def voice_name(self) -> str:
        """Description de la voix active (ex: "Hortense - French (Belgium)")."""
        return self._speaker.Voice.GetDescription()

    def _set_voice(self, voice_name: str | None) -> None:
        """Sélectionne la voix par nom, ou la première FR par défaut.

        Algorithme :
            1. Si voice_name est fourni → cherche une voix dont le nom contient voice_name
            2. Si pas trouvée ou pas de voice_name → cherche la première voix FR
            3. Si pas de voix FR → utilise la première voix du système
        """
        target_index: int | None = None

        if voice_name:
            # Recherche par nom (insensible à la casse)
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
        """Cherche l'index de la première voix française dans la collection.

        Compare l'identifiant de langue avec FRENCH_LANG_ID (0x040C).
        """
        for i in range(self._voices.Count):
            v = self._voices.Item(i)
            if _lang_id_to_int(v.GetAttribute("Language")) == FRENCH_LANG_ID:
                return i
        return None


class _Pyttsx3Backend:
    """pyttsx3 + eSpeak pour Linux / WSL.

    pyttsx3 est un wrapper multi-plateforme qui utilise eSpeak-ng
    sous Linux. Nécessite ``apt install espeak-ng``.

    Fonctionnement :
        1. Initialise le moteur pyttsx3
        2. Liste les voix disponibles
        3. Sélectionne la première voix FR
        4. speak() appelle engine.say() + engine.runAndWait()
    """

    def __init__(self, voice_name: str | None = None) -> None:
        import pyttsx3

        # Initialise le moteur TTS
        self._engine = pyttsx3.init()
        self._voice_name = ""
        # Sélectionne la voix (par nom ou première FR)
        self._set_voice(voice_name)

    def list_voices(self) -> list[dict]:
        """Liste les voix pyttsx3 (moins d'infos que SAPI)."""
        result: list[dict] = []
        for i, v in enumerate(self._engine.getProperty("voices")):
            result.append({
                "index": i,
                "description": v.name,
                "language_id": 0,  # pyttsx3 ne fournit pas toujours l'ID langue
            })
        return result

    def speak(self, text: str, blocking: bool) -> None:
        """Prononce le texte via pyttsx3.

        Si blocking=True, appelle runAndWait() qui attend la fin.
        Sinon, la synthèse est lancée en arrière-plan.
        """
        self._engine.say(text)
        if blocking:
            self._engine.runAndWait()

    def stop(self) -> None:
        """Arrête la synthèse en cours."""
        self._engine.stop()

    @property
    def voice_name(self) -> str:
        return self._voice_name

    def _set_voice(self, voice_name: str | None) -> None:
        """Sélectionne la voix par nom, ou la première FR par défaut.

        Algorithme similaire à _SapiBackend._set_voice mais utilise
        l'API pyttsx3 (getProperty/setProperty).
        """
        voices = self._engine.getProperty("voices")
        target = None

        if voice_name:
            # Recherche par nom
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
            # Cherche la première voix FR (identifiant contient "fr")
            for v in voices:
                if "fr" in v.id.lower():
                    target = v
                    break

        if target is None and voices:
            # Fallback : première voix disponible
            target = voices[0]

        if target:
            self._engine.setProperty("voice", target.id)
            self._voice_name = target.name
            log.info("Voix TTS selectionnee : %s", self._voice_name)


__all__ = ["TTS"]
