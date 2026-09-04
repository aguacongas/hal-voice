"""
Tests du point d'entrée __main__ (python -m hal_voice).

Les adapters et l'orchestrator sont mockés pour tester la logique de
composition (injection de dépendances) sans matériel audio.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import hal_voice.__main__ as entry
from hal_voice.adapters.config_loader import load_config_from_env
from hal_voice.domain.config import Config


def _fake_config() -> Config:
    return load_config_from_env()


def test_main_diagnose_returns_zero(monkeypatch) -> None:
    """--diagnose appelle pulse_diagnostics() et retourne 0."""
    monkeypatch.setattr("sys.argv", ["hal_voice", "--diagnose"])
    with patch.object(entry, "pulse_diagnostics") as diag:
        assert entry.main() == 0
    diag.assert_called_once()


def test_main_composes_orchestrator(monkeypatch) -> None:
    """main() injecte les adapters dans l'Orchestrator et lance run()."""
    monkeypatch.setattr("sys.argv", ["hal_voice"])

    cfg = _fake_config()
    mock_io = MagicMock()
    mock_stt = MagicMock()
    mock_tts = MagicMock()
    mock_parser = MagicMock()
    mock_orch = MagicMock()
    mock_orch.run.return_value = 0
    mock_wake = MagicMock()

    with (
        patch.object(entry, "load_config_from_env", return_value=cfg) as _cfg,
        patch.object(entry, "AudioIO", return_value=mock_io) as audioio_cls,
        patch.object(entry, "STT", return_value=mock_stt) as stt_cls,
        patch.object(entry, "TTS", return_value=mock_tts),
        patch.object(entry, "CommandParser", return_value=mock_parser),
        patch.object(entry, "WakeWordDetector", return_value=mock_wake),
        patch.object(entry, "Orchestrator", return_value=mock_orch) as orch_cls,
    ):
        result = entry.main()
        audioio_cls.assert_called_once_with(sample_rate=cfg.sample_rate)
        stt_cls.assert_called_once_with(model_path=cfg.vosk_model_path, sample_rate=cfg.sample_rate)
        orch_cls.assert_called_once_with(
            capture=mock_io,
            stt=mock_stt,
            tts=mock_tts,
            parser=mock_parser,
            silent=cfg.silent,
            wake_detector=mock_wake,
        )
        mock_orch.run.assert_called_once()

    assert result == 0
