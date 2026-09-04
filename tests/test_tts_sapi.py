"""
Tests TTS — sans dépendance matérielle pour les unitaires.

Les tests qui déclenchent réellement la synthèse vocale sont marqués
``requires_hardware`` (et ne sont joués que si la machine a une carte son).

Stratégie de mock :
    - Sur Windows : on mock win32com.client.Dispatch pour éviter d'appeler SAPI
    - Sur Linux : on mock pyttsx3.init pour éviter d'appeler eSpeak
    - Les tests vérifient que les bons appels sont faits (assert_called_with)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import hal_voice.adapters.tts as tts_mod
from hal_voice.adapters.tts import FRENCH_LANG_ID, TTS, _lang_id_to_int


def _make_fake_speaker():
    """Crée un fake speaker SAPI pour les tests Windows.

    Simule l'objet SpVoice avec :
        - GetVoices() → une collection vide par défaut
        - Voice → None par défaut
        - Speak() → ne fait rien (on vérifie juste les appels)
    """
    fake_speaker = MagicMock()
    fake_voices = MagicMock()
    fake_voices.Count = 0
    fake_voices.Item.return_value = MagicMock(
        GetDescription=MagicMock(return_value=""),
        GetAttribute=MagicMock(return_value="409"),
    )
    fake_speaker.GetVoices.return_value = fake_voices
    fake_speaker.Voice = None
    return fake_speaker


def _patch_win32com(monkeypatch, fake_speaker):
    """Remplace win32com.client par un mock dans le module tts_sapi.

    _win32com est win32com.client, donc _win32com.Dispatch(...) est l'appel
    qui crée l'objet SpVoice. On le remplace par notre fake.
    """
    mock_win32com = MagicMock()
    mock_win32com.Dispatch.return_value = fake_speaker
    monkeypatch.setattr(tts_mod, "_win32com", mock_win32com)


# ── Tests unitaires (communs à toutes les plateformes) ────────────────


def test_lang_id_to_int_hex_string() -> None:
    """_lang_id_to_int convertit les strings hexadécimales SAPI."""
    assert _lang_id_to_int("40C") == 1036  # Français
    assert _lang_id_to_int("409") == 1033  # Anglais US
    assert _lang_id_to_int("411") == 1041  # Japonais


def test_lang_id_to_int_int_passthrough() -> None:
    """_lang_id_to_int laisse passer les entiers tels quels."""
    assert _lang_id_to_int(1036) == 1036


def test_french_lang_id_value() -> None:
    """FRENCH_LANG_ID correspond bien au français (fr-FR)."""
    assert FRENCH_LANG_ID == 1036


# ── Tests Windows (SAPI 5) ────────────────────────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_tts_list_voices_with_mock(monkeypatch) -> None:
    """list_voices() renvoie les descriptions + language_id en int.

    Vérifie que les voix mockées (David EN, Hortense FR, Haruka JA)
    sont correctement parsées avec les bons identifiants de langue.
    """
    # Crée 3 voix mockées avec les bonnes langues
    david = MagicMock(
        GetDescription=MagicMock(return_value="David (English)"),
        GetAttribute=MagicMock(return_value="409"),
    )
    hortense = MagicMock(
        GetDescription=MagicMock(return_value="Hortense (French)"),
        GetAttribute=MagicMock(return_value="40C"),
    )
    haruka = MagicMock(
        GetDescription=MagicMock(return_value="Haruka (Japanese)"),
        GetAttribute=MagicMock(return_value="411"),
    )
    items = [david, hortense, haruka]

    fake_voices = MagicMock()
    fake_voices.Count = len(items)
    fake_voices.Item.side_effect = lambda i: items[i]

    fake_speaker = _make_fake_speaker()
    fake_speaker.GetVoices.return_value = fake_voices

    _patch_win32com(monkeypatch, fake_speaker)

    tts = TTS()
    voices = tts.list_voices()
    assert len(voices) == 3
    assert voices[0]["description"] == "David (English)"
    assert voices[0]["language_id"] == 1033  # Anglais US
    assert voices[1]["description"] == "Hortense (French)"
    assert voices[1]["language_id"] == 1036  # Français


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_tts_selects_french_voice_by_default(monkeypatch) -> None:
    """À l'init, TTS sélectionne la 1ère voix FR disponible.

    Par défaut, on cherche la voix française parmi toutes les voix.
    Si la première voix est EN et la deuxième FR, on doit prendre la FR.
    """
    david = MagicMock(
        GetDescription=MagicMock(return_value="David"),
        GetAttribute=MagicMock(return_value="409"),
    )
    hortense = MagicMock(
        GetDescription=MagicMock(return_value="Hortense"),
        GetAttribute=MagicMock(return_value="40C"),
    )
    items = [david, hortense]

    fake_voices = MagicMock()
    fake_voices.Count = len(items)
    fake_voices.Item.side_effect = lambda i: items[i]

    fake_speaker = _make_fake_speaker()
    fake_speaker.GetVoices.return_value = fake_voices

    _patch_win32com(monkeypatch, fake_speaker)

    TTS()
    # La voix française Hortense doit être sélectionnée
    assert fake_speaker.Voice == hortense


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_tts_speak_empty_text_noop(monkeypatch) -> None:
    """speak() avec un texte vide ne doit pas appeler SAPI.Speak.

    Évite les appels COM inutiles avec du texte vide ou whitespace.
    """
    fake_speaker = _make_fake_speaker()

    _patch_win32com(monkeypatch, fake_speaker)

    tts = TTS()
    fake_speaker.Speak.reset_mock()
    tts.speak("")
    tts.speak("   ")
    fake_speaker.Speak.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_tts_speak_calls_sapi(monkeypatch) -> None:
    """speak() non-vide appelle SAPI.Speak(text, flags).

    flags=0 pour blocking, flags=1 pour asynchrone.
    """
    fake_voices = MagicMock()
    fake_voices.Count = 1
    fake_voices.Item.return_value = MagicMock(
        GetDescription=MagicMock(return_value="Hortense"),
        GetAttribute=MagicMock(return_value="40C"),
    )

    fake_speaker = _make_fake_speaker()
    fake_speaker.GetVoices.return_value = fake_voices

    _patch_win32com(monkeypatch, fake_speaker)

    tts = TTS()
    fake_speaker.Speak.reset_mock()

    # Test blocking (flags=0)
    tts.speak("Bonjour", blocking=True)
    fake_speaker.Speak.assert_called_once_with("Bonjour", 0)

    fake_speaker.Speak.reset_mock()

    # Test asynchrone (flags=1)
    tts.speak("Hello", blocking=False)
    fake_speaker.Speak.assert_called_once_with("Hello", 1)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_tts_stop_calls_speak_with_purge(monkeypatch) -> None:
    """stop() appelle SAPI.Speak("", 2) pour purger la file."""
    fake_speaker = _make_fake_speaker()
    _patch_win32com(monkeypatch, fake_speaker)
    tts = TTS()
    fake_speaker.Speak.reset_mock()
    tts.stop()
    fake_speaker.Speak.assert_called_once_with("", 2)


# ── Tests Linux (pyttsx3) ─────────────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="Linux/WSL only")
def test_tts_pyttsx3_speak_empty_noop() -> None:
    """speak() avec un texte vide ne doit pas appeler pyttsx3."""
    mock_engine = MagicMock()
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.say.reset_mock()
    tts.speak("")
    tts.speak("   ")
    mock_engine.say.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Linux/WSL only")
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


@pytest.mark.skipif(sys.platform == "win32", reason="Linux/WSL only")
def test_tts_pyttsx3_stop() -> None:
    """stop() appelle engine.stop()."""
    mock_engine = MagicMock()
    with patch("pyttsx3.init", return_value=mock_engine):
        tts = TTS()
    mock_engine.stop.reset_mock()
    tts.stop()
    mock_engine.stop.assert_called_once()


# ── Test matériel (skippé si CI / pas de carte son) ───────────────────


@pytest.mark.requires_hardware
def test_tts_real_speak() -> None:
    """Vérifie qu'on arrive à instancier TTS et lister les voix réelles.

    Ce test nécessite une carte son fonctionnelle.
    Sur Windows, il utilise SAPI 5. Sur Linux, pyttsx3+eSpeak.
    """
    tts = TTS()
    voices = tts.list_voices()
    assert len(voices) >= 1
