"""
Tests TTS — pyttsx3 + eSpeak-ng (Linux/WSL2).

Le support Windows natif (SAPI 5 / win32com) a été retiré.
Les tests unitaires mockent ``pyttsx3.init`` pour éviter d'appeler eSpeak.
Les tests qui déclenchent réellement la synthèse sont marqués
``requires_hardware`` (et ne sont joués que si la machine a une carte son).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from hal_voice.adapters.tts import FRENCH_LANG_ID, TTS, _is_france, _is_french, _lang_id_to_int


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
