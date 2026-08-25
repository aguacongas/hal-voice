"""Tests TTS SAPI — sans dépendance matérielle pour les unitaires.

Les tests qui déclenchent réellement la synthèse vocale sont marqués
`requires_hardware` (et ne sont joués que si la machine a une carte son).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hal_voice.tts_sapi import FRENCH_LANG_ID, TTS, _lang_id_to_int


# ---------- Tests unitaires (sans SAPI) ----------


def test_lang_id_to_int_hex_string() -> None:
    assert _lang_id_to_int("40C") == 1036
    assert _lang_id_to_int("409") == 1033
    assert _lang_id_to_int("411") == 1041


def test_lang_id_to_int_int_passthrough() -> None:
    assert _lang_id_to_int(1036) == 1036


def test_french_lang_id_value() -> None:
    assert FRENCH_LANG_ID == 0x040C == 1036


def test_tts_list_voices_with_mock(monkeypatch) -> None:
    """list_voices doit renvoyer les descriptions + language_id en int."""
    david = MagicMock(GetDescription=MagicMock(return_value="David (English)"),
                      GetAttribute=MagicMock(return_value="409"))
    hortense = MagicMock(GetDescription=MagicMock(return_value="Hortense (French)"),
                         GetAttribute=MagicMock(return_value="40C"))
    haruka = MagicMock(GetDescription=MagicMock(return_value="Haruka (Japanese)"),
                       GetAttribute=MagicMock(return_value="411"))
    items = [david, hortense, haruka]

    fake_voices = MagicMock()
    fake_voices.Count = len(items)
    fake_voices.Item.side_effect = lambda i: items[i]

    fake_speaker = MagicMock()
    # GetVoices() appelé 1 fois dans __init__
    fake_speaker.GetVoices.return_value = fake_voices
    fake_speaker.Voice = None

    monkeypatch.setattr(
        "hal_voice.tts_sapi.win32com.client.Dispatch",
        lambda _: fake_speaker,
    )

    tts = TTS()
    voices = tts.list_voices()
    assert len(voices) == 3
    assert voices[0]["description"] == "David (English)"
    assert voices[0]["language_id"] == 1033
    assert voices[1]["description"] == "Hortense (French)"
    assert voices[1]["language_id"] == 1036


def test_tts_selects_french_voice_by_default(monkeypatch) -> None:
    """À l'init, TTS doit sélectionner la 1ère voix FR disponible."""
    david = MagicMock(GetDescription=MagicMock(return_value="David"),
                      GetAttribute=MagicMock(return_value="409"))
    hortense = MagicMock(GetDescription=MagicMock(return_value="Hortense"),
                         GetAttribute=MagicMock(return_value="40C"))
    items = [david, hortense]

    fake_voices = MagicMock()
    fake_voices.Count = len(items)
    fake_voices.Item.side_effect = lambda i: items[i]

    fake_speaker = MagicMock()
    fake_speaker.GetVoices.return_value = fake_voices
    fake_speaker.Voice = None

    monkeypatch.setattr(
        "hal_voice.tts_sapi.win32com.client.Dispatch",
        lambda _: fake_speaker,
    )

    TTS()
    # Speaker.Voice doit avoir été assigné à la voix Hortense
    assert fake_speaker.Voice == hortense


def test_tts_speak_empty_text_noop(monkeypatch) -> None:
    """speak() ne doit pas appeler SAPI.Speak si le texte est vide."""
    fake_speaker = MagicMock()
    fake_voices = MagicMock()
    fake_voices.Count = 0

    monkeypatch.setattr(
        "hal_voice.tts_sapi.win32com.client.Dispatch",
        lambda _: fake_speaker,
    )

    tts = TTS()
    fake_speaker.Speak.reset_mock()
    tts.speak("")
    tts.speak("   ")
    fake_speaker.Speak.assert_not_called()


def test_tts_speak_calls_sapi(monkeypatch) -> None:
    """speak() non-vide doit appeler SAPI.Speak(text, flags=0)."""
    fake_speaker = MagicMock()
    fake_voices = MagicMock()
    fake_voices.Count = 1
    fake_voices.Item.return_value = MagicMock(
        GetDescription=MagicMock(return_value="Hortense"),
        GetAttribute=MagicMock(return_value="40C"),
    )

    monkeypatch.setattr(
        "hal_voice.tts_sapi.win32com.client.Dispatch",
        lambda _: fake_speaker,
    )

    tts = TTS()
    fake_speaker.Speak.reset_mock()
    tts.speak("Bonjour", blocking=True)
    fake_speaker.Speak.assert_called_once_with("Bonjour", 0)

    fake_speaker.Speak.reset_mock()
    tts.speak("Hello", blocking=False)
    fake_speaker.Speak.assert_called_once_with("Hello", 1)


def test_tts_stop_calls_speak_with_purge(monkeypatch) -> None:
    fake_speaker = MagicMock()
    monkeypatch.setattr(
        "hal_voice.tts_sapi.win32com.client.Dispatch",
        lambda _: fake_speaker,
    )
    tts = TTS()
    fake_speaker.Speak.reset_mock()
    tts.stop()
    # flags=2 = SPF_PURGEBEFORESPEAK
    fake_speaker.Speak.assert_called_once_with("", 2)


# ---------- Test matériel (skippé si CI / pas de SAPI) ----------


@pytest.mark.requires_hardware
def test_tts_real_speak() -> None:
    """Vérifie qu'on arrive à instancier TTS et lister les voix réelles."""
    tts = TTS()
    voices = tts.list_voices()
    assert len(voices) >= 1
    # Vérifie qu'il existe au moins une voix FR
    has_french = any(v["language_id"] == 1036 for v in voices)
    assert has_french, "Aucune voix FR installée"
