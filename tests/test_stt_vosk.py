"""Tests STT Vosk — sans dépendance modèle pour les tests unitaires."""

from __future__ import annotations

import numpy as np
import pytest

from hal_voice.config import Config
from hal_voice.stt_vosk import STT


def test_instantiation_unloaded() -> None:
    stt = STT()
    assert stt.model_path is None


def test_load_missing_model_raises(tmp_path: pytest.TempPathFactory) -> None:

    cfg = Config(
        vosk_model_path=tmp_path / "does_not_exist",  # type: ignore[arg-type]
        sample_rate=16000,
        channels=1,
        dtype="int16",
        wake_word="hal",
    )
    stt = STT(cfg)
    with pytest.raises(FileNotFoundError, match="Modèle Vosk introuvable"):
        stt.load()


def test_transcribe_array_without_load_triggers_load(monkeypatch) -> None:
    """transcribe_array doit auto-charger si load() n'a pas été appelé."""
    stt = STT()

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
    monkeypatch.delenv("HAL_VOICE_MODEL_PATH", raising=False)
    cfg = Config.from_env()
    assert cfg.vosk_model_path.name == "vosk-model-small-fr-0.22"
    assert cfg.sample_rate == 16000


def test_config_from_env_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HAL_VOICE_MODEL_PATH", str(tmp_path / "custom_model"))
    monkeypatch.setenv("HAL_VOICE_SAMPLE_RATE", "8000")
    cfg = Config.from_env()
    assert cfg.vosk_model_path == tmp_path / "custom_model"
    assert cfg.sample_rate == 8000
