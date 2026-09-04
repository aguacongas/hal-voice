"""
Tests STT Vosk — sans dépendance modèle pour les tests unitaires.

Le modèle Vosk est lourd (~40 Mo) et nécessite un téléchargement.
Ces tests vérifient la logique du wrapper sans le modèle réel.

Les tests qui utilisent le vrai modèle sont marqués ``requires_hardware``.
"""

from __future__ import annotations

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
