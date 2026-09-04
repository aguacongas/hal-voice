"""
Tests STT Vosk — sans dépendance modèle pour les tests unitaires.

Le modèle Vosk est lourd (~40 Mo) et nécessite un téléchargement.
Ces tests vérifient la logique du wrapper sans le modèle réel.

Les tests qui utilisent le vrai modèle sont marqués ``requires_hardware``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from hal_voice.adapters.config_loader import load_config_from_env
from hal_voice.adapters.stt_vosk import STT


def test_instantiation_unloaded() -> None:
    """STT() sans argument n'a pas de modèle chargé."""
    stt = STT()
    assert stt.model_path is None


def test_load_missing_model_raises(tmp_path: pytest.TempPathFactory) -> None:
    """load() avec un chemin inexistant lève FileNotFoundError."""
    stt = STT(model_path=tmp_path / "does_not_exist", sample_rate=16000)
    with pytest.raises(FileNotFoundError, match="Modèle Vosk introuvable"):
        stt.load()


def test_transcribe_array_without_load_triggers_load(monkeypatch) -> None:
    """transcribe_array() auto-charge le modèle si load() n'a pas été appelé.

    Vérifie que le lazy loading fonctionne : si on n'a pas appelé load()
    manuellement, transcribe_array() le fait pour nous.
    """
    stt = STT()

    # Compteur pour vérifier que load() a bien été appelé une fois
    called = {"n": 0}

    def fake_load(model_path=None):
        called["n"] += 1
        raise RuntimeError("stop after load")  # preuve que load a été appelé

    monkeypatch.setattr(stt, "load", fake_load)
    audio = np.zeros(1600, dtype=np.int16)
    with pytest.raises(RuntimeError, match="stop after load"):
        stt.transcribe_array(audio)
    assert called["n"] == 1


def test_config_from_env_default(monkeypatch) -> None:
    """load_config_from_env() utilise les valeurs par défaut si pas de variable d'env."""
    monkeypatch.delenv("HAL_VOICE_MODEL_PATH", raising=False)
    cfg = load_config_from_env()
    assert cfg.vosk_model_path.name == "vosk-model-small-fr-0.22"
    assert cfg.sample_rate == 16000


def test_config_from_env_override(monkeypatch, tmp_path) -> None:
    """load_config_from_env() lit les variables d'environnement si définies."""
    monkeypatch.setenv("HAL_VOICE_MODEL_PATH", str(tmp_path / "custom_model"))
    monkeypatch.setenv("HAL_VOICE_SAMPLE_RATE", "8000")
    cfg = load_config_from_env()
    assert cfg.vosk_model_path == tmp_path / "custom_model"
    assert cfg.sample_rate == 8000


# ── Charge / transcription heureuses (vosk mocké) ────────────────────


def test_load_happy_path(monkeypatch, tmp_path) -> None:
    """load() construit le Model et le KaldiRecognizer pour un dossier existant."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_model = object()
    fake_rec = MagicMock()
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.Model", lambda p: fake_model)
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: fake_rec)
    stt = STT(model_path=model_dir, sample_rate=16000)
    stt.load()
    assert stt._model is fake_model
    assert stt._recognizer is fake_rec
    assert stt.model_path == model_dir
    fake_rec.SetWords.assert_called_once_with(True)


def test_load_is_idempotent_for_same_path(monkeypatch, tmp_path) -> None:
    """Charger deux fois le même chemin ne recrée pas le modèle."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    model_calls = []
    monkeypatch.setattr(
        "hal_voice.adapters.stt_vosk.Model", lambda p: model_calls.append(p) or object()
    )
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: MagicMock())
    stt = STT(model_path=model_dir, sample_rate=16000)
    stt.load()
    stt.load()
    assert len(model_calls) == 1


def test_load_none_path_raises_value_error() -> None:
    """load() sans chemin explicite ni configuré lève ValueError."""
    stt = STT()
    with pytest.raises(ValueError, match="Aucun chemin de modèle spécifié"):
        stt.load()


def test_transcribe_array_int16(monkeypatch, tmp_path) -> None:
    """transcribe_array() sur un buffer int16 renvoie le texte."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_rec = MagicMock()
    fake_rec.AcceptWaveform.return_value = 1
    fake_rec.FinalResult.return_value = '{"text": "bonjour le monde"}'
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.Model", lambda p: object())
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: fake_rec)
    stt = STT(model_path=model_dir, sample_rate=16000)

    audio = np.zeros(1600, dtype=np.int16)
    assert stt.transcribe_array(audio) == "bonjour le monde"
    fake_rec.AcceptWaveform.assert_called_once()


def test_transcribe_array_float_converts(monkeypatch, tmp_path) -> None:
    """transcribe_array() convertit un buffer float en int16."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_rec = MagicMock()
    fake_rec.FinalResult.return_value = '{"text": "texte"}'
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.Model", lambda p: object())
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: fake_rec)
    stt = STT(model_path=model_dir, sample_rate=16000)

    audio = np.zeros(1600, dtype=np.float64)
    assert stt.transcribe_array(audio) == "texte"
    # Vérifie que le buffer a bien été converti en int16 avant AcceptWaveform
    call_args, _ = fake_rec.AcceptWaveform.call_args
    converted = np.frombuffer(call_args[0], dtype=np.int16)
    assert converted.shape[0] == 1600


def test_transcribe_array_stereo_mixes(monkeypatch, tmp_path) -> None:
    """transcribe_array() moyenne les canaux pour un buffer stéréo."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_rec = MagicMock()
    fake_rec.FinalResult.return_value = '{"text": "x"}'
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.Model", lambda p: object())
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: fake_rec)
    stt = STT(model_path=model_dir, sample_rate=16000)

    audio = np.zeros((800, 2), dtype=np.int16)
    stt.transcribe_array(audio)
    call_args, _ = fake_rec.AcceptWaveform.call_args
    mono = np.frombuffer(call_args[0], dtype=np.int16)
    assert mono.shape[0] == 800  # mixé de (800, 2) → 800 mono


def test_transcribe_array_sample_rate_mismatch_logs(monkeypatch, tmp_path) -> None:
    """Un sample_rate différent provoque un log debug mais pas d'erreur."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_rec = MagicMock()
    fake_rec.FinalResult.return_value = '{"text": ""}'
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.Model", lambda p: object())
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: fake_rec)
    stt = STT(model_path=model_dir, sample_rate=16000)

    audio = np.zeros(1600, dtype=np.int16)
    assert stt.transcribe_array(audio, sample_rate=8000) == ""


def test_transcribe_file(monkeypatch, tmp_path) -> None:
    """transcribe_file() lit un WAV et transcrit avec le sample rate du fichier."""
    import soundfile as sf

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_rec = MagicMock()
    fake_rec.FinalResult.return_value = '{"text": "fichier lu"}'
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.Model", lambda p: object())
    monkeypatch.setattr("hal_voice.adapters.stt_vosk.KaldiRecognizer", lambda m, sr: fake_rec)
    monkeypatch.setattr(sf, "read", lambda p: (np.zeros(1600, dtype=np.float64), 8000))
    stt = STT(model_path=model_dir, sample_rate=16000)
    assert stt.transcribe_file("audio.wav") == "fichier lu"
