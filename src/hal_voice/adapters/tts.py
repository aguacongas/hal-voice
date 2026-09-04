"""
adapters.tts — Text-to-Speech (implémentation concrète).

Cible : Linux/WSL2 uniquement — pyttsx3 + eSpeak-ng
(nécessite ``apt install espeak-ng``).

Le support Windows natif (SAPI 5 / win32com) a été retiré : l'app
tourne sous WSL2 et l'audio passe par PulseAudio for Windows (hôte),
pas par les voix SAPI de Windows.

Vérifie le protocole domain.protocols.ITTS.

Architecture :
    TTS est une facade qui délègue au backend _Pyttsx3Backend
    (pyttsx3, qui utilise eSpeak-ng sous Linux).

Sélection de la voix :
    - Si voice_name est fourni, on cherche la voix correspondante
    - Sinon, on prend la voix FRANCE prioritaire (Sinon Belgique/Suisse)
    - Fallback : la première voix du système

WSL2 / PulseAudio :
    eSpeak-ng utilise ALSA par défaut pour la sortie audio. Sous WSL2,
    ALSA n'a pas de carte son → erreurs. Fix : on force PulseAudio via
    les variables d'environnement PULSE_SERVER + un ~/.asoundrc avant
    l'initialisation de pyttsx3.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# Identifiant de langue français (0x040C = 1036)
FRENCH_LANG_ID = 0x040C


def _lang_id_to_int(value: str | int) -> int:
    """Convertit un identifiant de langue en entier (utile aux voix eSpeak).

    Accepte les strings hexadécimales ('40C') et les entiers.
    Les tags BCP 47 (ex: 'roa/fr') ne sont pas hex → retourne 0.
    """
    if isinstance(value, int):
        return value
    try:
        return int(value, 16)
    except (ValueError, TypeError):
        return 0


def _is_french(value: str | int) -> bool:
    """Détecte si un identifiant de langue correspond au français.

    Gère deux formats :
    - hex SAPI : string hex ('40C') ou entier (1036) → FRENCH_LANG_ID
    - pyttsx3/eSpeak : IDs BCP 47 ('roa/fr', 'roa/fr-be', 'fr', 'fra')
      → vérifie la présence d'un tag 'fr' isolé
    """
    if isinstance(value, int):
        return value == FRENCH_LANG_ID
    try:
        if int(value, 16) == FRENCH_LANG_ID:
            return True
    except (ValueError, TypeError):
        pass
    # BCP 47 / eSpeak : token 'fr' (fr, fr-fr, fr/roa, roa/fr, fra...)
    s = str(value).strip().lower().replace("_", "-").replace("/", "-")
    tokens = {t for t in s.split("-") if t}
    return "fr" in tokens or "fra" in tokens or "fre" in tokens


def _is_france(value: str | int) -> bool:
    """Détecte spécifiquement le français de France (pas Belgique/Suisse).

    - hex SAPI : LANGID 0x040C (1036) = français (France).
    - eSpeak : 'roa/fr' (France) vs 'roa/fr-be' / 'roa/fr-ch'.
    """
    if isinstance(value, int):
        return value == FRENCH_LANG_ID
    try:
        if int(value, 16) == FRENCH_LANG_ID:
            return True
    except (ValueError, TypeError):
        pass
    s = str(value).strip().lower().replace("_", "-").replace("/", "-")
    parts = s.split("-")
    # France si le dernier token est exactement 'fr' (et pas 'fr-be'/'fr-ch')
    return parts[-1] == "fr" and not parts[-1].endswith(("be", "ch"))


def _select_voice(setter, voices, voice_name: str | None, get_desc, get_attr, set_prop) -> str:
    """Logique commune de sélection de voix.

    1. Si voice_name fourni → cherche par nom
    2. Sinon → voix FRANCE prioritaire ('roa/fr' / 0x040C)
    3. Sinon → n'importe quelle voix FR (Belgique, Suisse, ...)
    4. Fallback → première voix du système
    """
    target = None
    if voice_name:
        for v in voices:
            if voice_name.lower() in get_desc(v).lower():
                target = v
                break
        if target is None:
            log.warning("Voix %r introuvable, fallback sur la 1ere voix FR.", voice_name)

    # Priorité : français de France
    if target is None:
        for v in voices:
            if _is_france(get_attr(v)):
                target = v
                break
        if target is not None:
            log.info("Voix FR (France) trouvée.")

    # Sinon : n'importe quel français
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
    (via le serveur PulseAudio for Windows de l'hôte) au lieu de WSLg
    ou ALSA.

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

    # Récupère l'IP de l'hôte Windows (gateway)
    import subprocess

    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True, stderr=subprocess.DEVNULL
        )
        host_ip = out.split()[2]
    except (subprocess.CalledProcessError, IndexError, FileNotFoundError):
        return

    tcp_server = f"tcp:{host_ip}"

    # Teste si PulseAudio (TCP) est accessible
    try:
        subprocess.run(
            ["pactl", "info"],
            env={**os.environ, "PULSE_SERVER": tcp_server},
            capture_output=True,
            timeout=3,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("PulseAudio inaccessible — eSpeak peut échouer (erreurs ALSA)")
        return

    # Force eSpeak-ng à utiliser PulseAudio
    os.environ["PULSE_SERVER"] = tcp_server

    # Redirige le device ALSA par défaut vers PulseAudio.
    # pyttsx3/eSpeak joue l'audio via `aplay <wav>` (ALSA sans -D).
    # Sans carte son, ALSA échoue ("cannot find card 0"). Un ~/.asoundrc
    # qui pointe `pcm.!default` vers le plugin `pulse` (libasound2-plugins)
    # fait passer aplay par PulseAudio + PULSE_SERVER → audible.
    _write_asoundrc()
    log.info("eSpeak configuré pour PulseAudio : %s", tcp_server)


_ASOUNDRC = """\
pcm.!default {
    type pulse
    hint {
        show on
        description "Default ALSA Output (PulseAudio)"
    }
}
ctl.!default {
    type pulse
}
"""


def _write_asoundrc() -> None:
    """Écrit ~/.asoundrc pour rediriger ALSA → PulseAudio (résout les erreurs aplay).

    Idempotent : n'écrit que si le fichier n'existe pas déjà.
    """
    asoundrc = Path.home() / ".asoundrc"
    try:
        if asoundrc.exists():
            log.debug("~/.asoundrc déjà présent, skip")
            return
        asoundrc.write_text(_ASOUNDRC)
        log.info("~/.asoundrc créé — ALSA redirigé vers PulseAudio")
    except OSError:
        log.warning("Impossible d'écrire ~/.asoundrc (%s)", asoundrc)


class TTS:
    """Wrapper TTS (pyttsx3 + eSpeak-ng) — Linux/WSL2."""

    def __init__(self, voice_name: str | None = None) -> None:
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
            result.append(
                {
                    "index": i,
                    "description": v.name,
                    "language_id": _lang_id_to_int(v.id),
                }
            )
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
