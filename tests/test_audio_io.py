"""
Tests audio_io — sans dépendance matérielle pour les tests unitaires.
Utilise sounddevice et mocks pour valider le comportement.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import sounddevice as sd

from hal_voice.adapters import audio_io as entry
from hal_voice.adapters.audio_io import AudioIO
from hal_voice.domain.config import DEFAULT_CHANNELS, DEFAULT_DTYPE, DEFAULT_SAMPLE_RATE


def test_default_constants() -> None:
    """Vérifie que les constantes audio sont bien définies."""
    assert DEFAULT_SAMPLE_RATE == 16000
    assert DEFAULT_CHANNELS == 1
    assert DEFAULT_DTYPE == "int16"


def test_instantiation_uses_defaults() -> None:
    """AudioIO() sans argument utilise les constantes par défaut."""
    io = AudioIO()
    assert io.sample_rate == DEFAULT_SAMPLE_RATE
    assert io.channels == DEFAULT_CHANNELS
    assert io.dtype == DEFAULT_DTYPE


def test_instantiation_accepts_overrides() -> None:
    """AudioIO() accepte des paramètres personnalisés."""
    io = AudioIO(sample_rate=48000, channels=2, dtype="float32")
    assert io.sample_rate == 48000
    assert io.channels == 2
    assert io.dtype == "float32"


def test_list_devices_returns_list(monkeypatch) -> None:
    """list_devices() retourne la liste des devices audio."""
    fake_devices = [{"name": "Mic 1", "hostapi": 0}, {"name": "Speaker 1", "hostapi": 0}]
    monkeypatch.setattr(sd, "query_devices", lambda: fake_devices)

    io = AudioIO()
    devices = io.list_devices()
    assert isinstance(devices, list)
    assert len(devices) == 2
    assert devices[0]["name"] == "Mic 1"
    assert devices[0]["index"] == 0


def test_default_names(monkeypatch) -> None:
    """default_input_name / default_output_name retournent les noms des devices."""
    monkeypatch.setattr(sd, "query_devices", lambda device_id: {"name": f"Dev {device_id}"})

    io = AudioIO(input_device=1, output_device=2)
    assert io.default_input_name() == "Dev 1"
    assert io.default_output_name() == "Dev 2"


def test_default_names_fallback_unknown(monkeypatch) -> None:
    """En cas d'erreur sur query_devices, on renvoie 'unknown'."""
    monkeypatch.setattr(sd, "query_devices", MagicMock(side_effect=Exception("boom")))

    io = AudioIO()
    assert io.default_input_name() == "unknown"
    assert io.default_output_name() == "unknown"


# ── Capture ──────────────────────────────────────────────────────


def test_record_calls_sd_rec(monkeypatch) -> None:
    """record() appelle sd.rec avec les bons paramètres."""
    # On mock sd.rec pour renvoyer un array de la bonne taille
    n_samples = int(0.5 * DEFAULT_SAMPLE_RATE)
    mock_audio = np.zeros(n_samples, dtype=np.int16)

    monkeypatch.setattr(sd, "rec", MagicMock(return_value=mock_audio))
    monkeypatch.setattr(sd, "wait", MagicMock())

    io = AudioIO()
    audio = io.record(duration_seconds=0.5)

    sd.rec.assert_called_once_with(
        n_samples,
        samplerate=DEFAULT_SAMPLE_RATE,
        channels=DEFAULT_CHANNELS,
        dtype=np.int16,
        device=io._input_id,
    )
    assert audio.shape == (n_samples, 1)


def test_record_handles_exception(monkeypatch) -> None:
    """Si sd.rec échoue, record() renvoie du silence."""
    monkeypatch.setattr(sd, "rec", MagicMock(side_effect=Exception("Audio Error")))

    io = AudioIO()
    audio = io.record(duration_seconds=0.25)

    n = int(0.25 * DEFAULT_SAMPLE_RATE)
    assert audio.shape == (n, 1)
    assert (audio == 0).all()


# ── Lecture ──────────────────────────────────────────────────────


def test_play_calls_sd_play(monkeypatch) -> None:
    """play() appelle sd.play et sd.wait."""
    monkeypatch.setattr(sd, "play", MagicMock())
    monkeypatch.setattr(sd, "wait", MagicMock())

    io = AudioIO()
    data = np.zeros(100, dtype=np.int16)
    io.play(data)

    sd.play.assert_called_once()
    sd.wait.assert_called_once()


def test_play_handles_exception(monkeypatch) -> None:
    """Si sd.play échoue, play() ne lève pas d'exception."""
    monkeypatch.setattr(sd, "play", MagicMock(side_effect=Exception("Play Error")))

    io = AudioIO()
    data = np.zeros(100, dtype=np.int16)
    # Ne doit pas planter
    io.play(data)


# ── Fichiers ────────────────────────────────────────────────────


def test_record_to_file_delegates(tmp_path, monkeypatch) -> None:
    """record_to_file appelle record et sf.write."""
    io = AudioIO()
    # Mock record pour éviter l'appel au hardware
    monkeypatch.setattr(io, "record", lambda duration: np.zeros((16000, 1), dtype=np.int16))
    # Mock sf.write
    import soundfile as sf

    monkeypatch.setattr(sf, "write", MagicMock())

    out_path = tmp_path / "test.wav"
    result = io.record_to_file(out_path, 1.0)

    assert result == out_path
    sf.write.assert_called_once()


def test_play_file_delegates(monkeypatch) -> None:
    """play_file lit le fichier et appelle play."""
    io = AudioIO()

    # Mock sf.read pour renvoyer un faux audio
    import soundfile as sf

    fake_audio = np.zeros((100, 1), dtype=np.float32)
    monkeypatch.setattr(sf, "read", lambda p: (fake_audio, 16000))

    # Mock io.play
    monkeypatch.setattr(io, "play", MagicMock())

    io.play_file("fake.wav")
    io.play.assert_called_once()


def test_play_file_stereo_to_mono(monkeypatch) -> None:
    """play_file réduit un flux stéréo en mono quand channels == 1."""
    io = AudioIO(channels=1)

    import soundfile as sf

    fake_stereo = np.ones((100, 2), dtype=np.float64)
    monkeypatch.setattr(sf, "read", lambda p: (fake_stereo, 16000))
    monkeypatch.setattr(io, "play", MagicMock())

    io.play_file("fake.wav")
    played = io.play.call_args[0][0]
    assert played.shape == (100,)
    assert played.dtype == np.int16


# ── quick_test (boucle manuelle 5s) ──────────────────────────────


def test_quick_test_with_sound(monkeypatch, capsys) -> None:
    """quick_test() avec un signal audible joue l'audio capturé."""
    fake_audio = np.full((16000, 1), 1000, dtype=np.int16)
    io = AudioIO()
    monkeypatch.setattr(entry, "AudioIO", lambda **kw: io)
    monkeypatch.setattr(io, "record", lambda d: fake_audio)
    monkeypatch.setattr(io, "play", MagicMock())

    entry.quick_test()

    output = capsys.readouterr().out
    assert "max amplitude" in output
    assert "Replay" in output
    io.play.assert_called_once_with(fake_audio)


def test_quick_test_silent(monkeypatch, capsys) -> None:
    """quick_test() sans signal (silence) n'appelle pas play."""
    silent = np.zeros((16000, 1), dtype=np.int16)
    io = AudioIO()
    monkeypatch.setattr(entry, "AudioIO", lambda **kw: io)
    monkeypatch.setattr(io, "record", lambda d: silent)
    monkeypatch.setattr(io, "play", MagicMock())

    entry.quick_test()

    output = capsys.readouterr().out
    assert "Aucun son capté" in output
    io.play.assert_not_called()
