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

WSL2 / PulseAudio :
    eSpeak-ng utilise ALSA par défaut pour la sortie audio. Sous WSL2,
    ALSA n'a pas de carte son → erreurs. Fix : on force PulseAudio via
    les variables d'environnement PULSE_SERVER + ESPEAK_DATA_PATH avant
    l'initialisation de pyttsx3.
"""

from __future__ import annotations

import logging
import os
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


def _is_french(value: str | int) -> bool:
    """Détecte si un identifiant de langue correspond au français.

    Gère les trois formats :
    - SAPI 5 : hex string ('40C') ou entier (1036) → compare avec FRENCH_LANG_ID
    - pyttsx3/eSpeak : IDs BCP 47 ('roa/fr', 'roa/fr-be', 'fr', 'fra')
      → vérifie la présence d'un tag 'fr' isolé
    """
    if isinstance(value, int):
        return value == FRENCH_LANG_ID
    # SAPI hex
    try:
        return int(value, 16) == FRENCH_LANG_ID
    except (ValueError, TypeError):
        pass
    # BCP 47 / eSpeak : token 'fr' (fr, fr-fr, fr/roa, roa/fr, fra...)
    s = str(value).strip().lower().replace("_", "-").replace("/", "-")
    tokens = {t for t in s.split("-") if t}
    return "fr" in tokens or "fra" in tokens or "fre" in tokens


def _select_voice(setter, voices, voice_name: str | None, get_desc, get_attr, set_prop) -> str:
    """Logique commune de sélection de voix.

    1. Si voice_name fourni → cherche par nom
    2. Sinon → première voix FR (supporte SAPI hex + BCP 47)
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
            if _is_french(get_attr(v)):
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


def _configure_pulse_for_espeak() -> None:
    """Configure PulseAudio comme sortie audio pour eSpeak-ng sous WSL2.

    eSpeak-ng utilise ALSA par défaut. Sous WSL2, ALSA n'a pas de carte
    son → erreurs ALSA. Cette fonction force eSpeak à utiliser PulseAudio
    Windows (TCP) au lieu de WSLg ou ALSA.

    À appeler AVANT l'import de pyttsx3.
    """
    # Détecte WSL2
    try:
        with open("/proc/version") as f:
            is_wsl = "microsoft" in f.read().lower()
    except OSError:
        is_wsl = False

    if not is_wsl:
        return

    # Récupère l'IP Windows (gateway)
    import subprocess

    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True, stderr=subprocess.DEVNULL
        )
        host_ip = out.split()[2]
    except (subprocess.CalledProcessError, IndexError, FileNotFoundError):
        return

    tcp_server = f"tcp:{host_ip}"

    # Teste si PulseAudio Windows (TCP) est accessible — préféré à WSLg
    try:
        subprocess.run(
            ["pactl", "info"],
            env={**os.environ, "PULSE_SERVER": tcp_server},
            capture_output=True,
            timeout=3,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("PulseAudio Windows inaccessible — eSpeak peut échouer (erreurs ALSA)")
        return

    # Force eSpeak-ng à utiliser PulseAudio Windows
    os.environ["PULSE_SERVER"] = tcp_server
    log.info("eSpeak configuré pour PulseAudio Windows : %s", tcp_server)


class TTS:
    """Wrapper TTS multi-plateforme.

    SAPI 5 sur Windows, pyttsx3+eSpeak sur Linux/WSL.
    Le backend est choisi automatiquement selon ``sys.platform``.
    """

    def __init__(self, voice_name: str | None = None) -> None:
        if sys.platform == "win32":
            self._backend = _SapiBackend(voice_name)
        else:
            _configure_pulse_for_espeak()
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
