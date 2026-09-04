"""
Tests TTS — pyttsx3 + eSpeak-ng (Linux/WSL2).

Le support Windows natif (SAPI 5 / win32com) a été retiré.
Les tests unitaires mockent ``pyttsx3.init`` pour éviter d'appeler eSpeak.
Les tests qui déclenchent réellement la synthèse sont marqués
``requires_hardware`` (et ne sont joués que si la machine a une carte son).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from hal_voice.adapters.tts import (
    FRENCH_LANG_ID,
    TTS,
    _configure_pulse_for_espeak,
    _is_france,
    _is_french,
    _lang_id_to_int,
    _select_voice,
)


def _voice(voice_id: str, name: str) -> SimpleNamespace:
    """Crée un objet voix factice de type pyttsx3 (id + name)."""
    return SimpleNamespace(id=voice_id, name=name)


# ── Tests unitaires (langue / helpers) ────────────────────────────────


def test_lang_id_to_int_hex_string() -> None:
    """_lang_id_to_int convertit les strings hexadécimales SAPI."""
    assert _lang_id_to_int("40C") == 1036  # Français
    assert _lang_id_to_int("409") == 1033  # Anglais US
    assert _lang_id_to_int("411") == 1041  # Japonais


def test_lang_id_to_int_int_passthrough() -> None:
    """_lang_id_to_int laisse passer les entiers tels quels."""
    assert _lang_id_to_int(1036) == 1036


def test_lang_id_to_int_bcp47_returns_zero() -> None:
    """_lang_id_to_int ne parse pas les tags BCP 47 → 0."""
    assert _lang_id_to_int("roa/fr") == 0
    assert _lang_id_to_int("gmw/en") == 0


def test_french_lang_id_value() -> None:
    """FRENCH_LANG_ID correspond bien au français (fr-FR)."""
    assert FRENCH_LANG_ID == 1036


def test_is_french_sapi_hex() -> None:
    """_is_french reconnaît les IDs SAPI hex (fr-FR = 40C)."""
    assert _is_french("40C")
    assert not _is_french("409")  # en-US


def test_is_french_bcp47() -> None:
    """_is_french reconnaît les tags BCP 47 / eSpeak."""
    assert _is_french("roa/fr")
    assert _is_french("roa/fr-be")
    assert _is_french("fr")
    assert _is_french("fra")
    assert not _is_french("roa/en")
    assert not _is_french("gmw/en")


def test_is_france_prefers_metropole() -> None:
    """_is_france cible uniquement le français de France (pas BE/CH)."""
    # hex : fr-FR = 0x040C
    assert _is_france("40C")
    # eSpeak : roa/fr = France ; fr-be/fr-ch = Belgique/Suisse
    assert _is_france("roa/fr")
    assert not _is_france("roa/fr-be")
    assert not _is_france("roa/fr-ch")
    assert not _is_france("roa/en")


def test_write_asoundrc(tmp_path, monkeypatch) -> None:
    """_write_asoundrc crée ~/.asoundrc pointant vers PulseAudio."""
    monkeypatch.setattr("hal_voice.adapters.tts.Path.home", lambda: tmp_path)
    asoundrc = tmp_path / ".asoundrc"
    assert not asoundrc.exists()

    from hal_voice.adapters.tts import _write_asoundrc

    _write_asoundrc()
    assert asoundrc.exists()
    assert "type pulse" in asoundrc.read_text()
    _write_asoundrc()  # idempotent, ne doit pas lever


# ── Tests pyttsx3 (backend Linux/WSL) ─────────────────────────────────


def test_tts_pyttsx3_init_selects_french() -> None:
    """À l'init, TTS sélectionne la voix française (France)."""
    mock_engine = MagicMock()
    voices = [_voice("gmw/en", "English"), _voice("roa/fr", "French")]
    mock_engine.getProperty.return_value = voices
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    # Doit choisir la voix France (roa/fr)
    mock_engine.setProperty.assert_called_with("voice", "roa/fr")
    assert tts.voice_name == "French"


def test_tts_pyttsx3_init_fallback_french_belgium() -> None:
    """Si pas de voix France, prend une autre voix FR (Belgique)."""
    mock_engine = MagicMock()
    voices = [_voice("gmw/en", "English"), _voice("roa/fr-be", "French (Belgium)")]
    mock_engine.getProperty.return_value = voices
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.setProperty.assert_called_with("voice", "roa/fr-be")
    assert tts.voice_name == "French (Belgium)"


def test_tts_pyttsx3_speak_empty_noop() -> None:
    """speak() avec un texte vide ne doit pas appeler pyttsx3."""
    mock_engine = MagicMock()
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.say.reset_mock()
    tts.speak("")
    tts.speak("   ")
    mock_engine.say.assert_not_called()


def test_tts_pyttsx3_speak_calls_engine() -> None:
    """speak() non-vide appelle engine.say() + runAndWait() (blocking)."""
    mock_engine = MagicMock()
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.say.reset_mock()
    mock_engine.runAndWait.reset_mock()
    tts.speak("Bonjour", blocking=True)
    mock_engine.say.assert_called_once_with("Bonjour")
    mock_engine.runAndWait.assert_called_once()


def test_tts_pyttsx3_nonblocking_skips_run_and_wait() -> None:
    """speak(blocking=False) n'appelle pas runAndWait()."""
    mock_engine = MagicMock()
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.runAndWait.reset_mock()
    tts.speak("Hi", blocking=False)
    mock_engine.say.assert_called_once_with("Hi")
    mock_engine.runAndWait.assert_not_called()


def test_tts_pyttsx3_stop() -> None:
    """stop() appelle engine.stop()."""
    mock_engine = MagicMock()
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.stop.reset_mock()
    tts.stop()
    mock_engine.stop.assert_called_once()


def test_tts_list_voices() -> None:
    """list_voices() renvoie descriptions + language_id."""
    mock_engine = MagicMock()
    voices = [_voice("roa/fr", "French"), _voice("gmw/en", "English")]
    mock_engine.getProperty.return_value = voices
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    result = tts.list_voices()
    assert len(result) == 2
    assert result[0]["description"] == "French"
    # language_id basé sur l'id eSpeak (BCP 47 → 0 via _lang_id_to_int)
    assert result[0]["language_id"] == 0


# ── Test matériel (skippé si CI / pas de carte son) ───────────────────


@pytest.mark.requires_hardware
def test_tts_real_speak() -> None:
    """Vérifie qu'on arrive à instancier TTS et lister les voix réelles."""
    tts = TTS()
    voices = tts.list_voices()
    assert len(voices) >= 1


# ── _select_voice (logique de sélection) ─────────────────────────────


def test_select_voice_by_name() -> None:
    """voice_name fourni → on sélectionne la voix correspondante."""
    voices = [_voice("gmw/en", "English"), _voice("roa/fr", "French")]
    set_prop = MagicMock()
    result = _select_voice(voices, "French", lambda v: v.name, lambda v: v.id, set_prop)
    assert result == "French"
    set_prop.assert_called_once_with(_voice("roa/fr", "French"))


def test_select_voice_name_not_found_falls_to_france() -> None:
    """voice_name introuvable → warning puis voix FR (France)."""
    voices = [_voice("gmw/en", "English"), _voice("roa/fr", "French")]
    set_prop = MagicMock()
    result = _select_voice(voices, "Existe pas", lambda v: v.name, lambda v: v.id, set_prop)
    assert result == "French"
    set_prop.assert_called_once_with(_voice("roa/fr", "French"))


def test_select_voice_prefers_france_over_other_french() -> None:
    """Sans voice_name, on préfère la voix France avant la Belgique."""
    voices = [_voice("roa/fr-be", "French (Belgium)"), _voice("roa/fr", "French")]
    set_prop = MagicMock()
    result = _select_voice(voices, None, lambda v: v.name, lambda v: v.id, set_prop)
    assert result == "French"
    set_prop.assert_called_once_with(_voice("roa/fr", "French"))


def test_select_voice_any_french_when_no_france() -> None:
    """Sans voix France, on prend n'importe quelle voix FR (Belgique)."""
    voices = [_voice("roa/fr-be", "French (Belgium)")]
    set_prop = MagicMock()
    result = _select_voice(voices, None, lambda v: v.name, lambda v: v.id, set_prop)
    assert result == "French (Belgium)"


def test_select_voice_fallback_first_voice() -> None:
    """Sans aucune voix FR, on retombe sur la première voix du système."""
    voices = [_voice("gmw/en", "English"), _voice("tr", "Turkish")]
    set_prop = MagicMock()
    result = _select_voice(voices, None, lambda v: v.name, lambda v: v.id, set_prop)
    assert result == "English"
    set_prop.assert_called_once_with(_voice("gmw/en", "English"))


def test_select_voice_empty_returns_empty() -> None:
    """Aucune voix disponible → retourne chaîne vide."""
    set_prop = MagicMock()
    result = _select_voice([], None, lambda v: v.name, lambda v: v.id, set_prop)
    assert result == ""
    set_prop.assert_not_called()


# ── _configure_pulse_for_espeak (branches) ────────────────────────────


def test_configure_pulse_returns_when_oserror(monkeypatch) -> None:
    """open(/proc/version) en OSError → pas WSL → return silencieux."""
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: (_ for _ in ()).throw(OSError("nope")))
    _configure_pulse_for_espeak()  # ne doit pas lever


def test_configure_pulse_returns_when_not_wsl(monkeypatch) -> None:
    """/proc/version sans 'microsoft' → pas WSL → return silencieux."""
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: _TextIO("debian GNU/Linux"))
    _configure_pulse_for_espeak()


def test_configure_pulse_returns_when_no_host_ip(monkeypatch) -> None:
    """WSL mais `ip route` échoue → return silencieux."""
    import subprocess as sp

    monkeypatch.setattr("builtins.open", lambda p, *a, **k: _TextIO("microsoft WSL2"))

    def _fail(*a, **k):
        raise FileNotFoundError("ip")

    # PATCH global du module subprocess réel (le tts fait un import lazy).
    monkeypatch.setattr(sp, "check_output", _fail)
    _configure_pulse_for_espeak()


def test_configure_pulse_logs_when_unreachable(monkeypatch) -> None:
    """PulseAudio TCP inaccessible → warning, pas d'erreur, pas d'asoundrc."""
    import subprocess as sp

    monkeypatch.setattr("builtins.open", lambda p, *a, **k: _TextIO("microsoft WSL2"))
    monkeypatch.setattr(sp, "check_output", lambda *a, **k: "default via 172.20.1.1 dev eth0")
    monkeypatch.setattr(
        sp, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("pactl"))
    )
    with patch("logging.getLogger") as _lg:
        _configure_pulse_for_espeak()  # ne doit pas lever


def test_configure_pulse_happy_path(monkeypatch) -> None:
    """WSL + IP + pactl OK → set PULSE_SERVER et écrit ~/.asoundrc."""
    import subprocess as sp

    monkeypatch.setattr("builtins.open", lambda p, *a, **k: _TextIO("microsoft WSL2"))
    monkeypatch.setattr(sp, "check_output", lambda *a, **k: "default via 172.20.1.1 dev eth0")
    monkeypatch.setattr(sp, "run", MagicMock())
    monkeypatch.setattr("hal_voice.adapters.tts._write_asoundrc", MagicMock())
    _configure_pulse_for_espeak()
    assert os.environ.get("PULSE_SERVER") == "tcp:172.20.1.1"


def test_write_asoundrc_oserror(tmp_path, monkeypatch) -> None:
    """Si ~/.asoundrc est inscriptible → warning, pas d'erreur."""
    monkeypatch.setattr("hal_voice.adapters.tts.Path.home", lambda: tmp_path)
    asoundrc = tmp_path / ".asoundrc"
    asoundrc.mkdir()  # un dossier au lieu d'un fichier → write_text échoue
    from hal_voice.adapters.tts import _write_asoundrc

    _write_asoundrc()  # ne doit pas lever


class _TextIO:
    """Petit substitut de fichier pour le mock de open()."""

    def __init__(self, content: str) -> None:
        self._content = content

    def read(self) -> str:
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
