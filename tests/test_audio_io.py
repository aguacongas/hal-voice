"""
Tests audio_io — sans dépendance matérielle pour les tests unitaires.

Les tests qui capturent réellement le micro sont marqués ``requires_hardware``
et ne sont joués que sur les machines avec une carte son active.

Marqueurs pytest utilisés :
    - requires_hardware : nécessite un micro fonctionnel
    - requires_windows  : spécifique à Windows (SAPI 5, PortAudio)
"""

from __future__ import annotations

import numpy as np
import pytest

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


def test_list_devices_returns_list() -> None:
    """list_devices() retourne au moins un device audio."""
    io = AudioIO()
    devices = io.list_devices()
    # sounddevice renvoie un DeviceList (sequence-like), pas une vraie list
    assert len(devices) >= 1
    assert devices[0]["name"]
    assert "max_input_channels" in devices[0]


@pytest.mark.requires_hardware
def test_record_returns_correct_shape() -> None:
    """record() retourne un array int16 de la bonne forme.

    Shape attendue : (n_samples, 1) où n_samples = duration × sample_rate.
    Le 2e dimension (1) est pour le canal mono.
    """
    io = AudioIO()
    audio = io.record(duration_seconds=0.5)
    assert audio.shape == (int(0.5 * DEFAULT_SAMPLE_RATE), 1)
    assert audio.dtype.name == "int16"


# ── Gestion d'erreurs audio (device indisponible) ────────────────────


def test_record_sounddevice_returns_silence_on_error(monkeypatch) -> None:
    """Si sounddevice échoue, _record_sounddevice renvoie du silence."""
    io = AudioIO()
    io._use_pulse = False

    def _boom(*a, **k):
        raise OSError("device inconnu")

    monkeypatch.setattr("hal_voice.adapters.audio_io.sd.rec", _boom)
    audio = io._record_sounddevice(1.0)
    assert audio.dtype.name == "int16"
    assert (audio == 0).all()


def test_record_pulse_returns_silence_without_device() -> None:
    """Sans device PulseAudio, record() renvoie un buffer de silence."""
    io = AudioIO()
    io._use_pulse = True
    io._pulse_input = None
    audio = io.record(duration_seconds=0.25)
    n = int(0.25 * DEFAULT_SAMPLE_RATE)
    assert audio.shape == (n, 1)
    assert (audio == 0).all()


def test_record_pulse_handles_missing_parecord(monkeypatch) -> None:
    """Si parecord est introuvable, record() renvoie du silence."""
    io = AudioIO()
    io._use_pulse = True
    io._pulse_input = "wavein"
    io._pulse_server = None

    def _raising_popen(*a, **k):
        raise FileNotFoundError("parecord")

    monkeypatch.setattr("hal_voice.adapters.audio_io.subprocess.Popen", _raising_popen)
    audio = io.record(0.25)
    n = int(0.25 * DEFAULT_SAMPLE_RATE)
    assert audio.shape == (n, 1)
    assert (audio == 0).all()


def test_play_sounddevice_ignores_error(monkeypatch) -> None:
    """Si la lecture sounddevice échoue, play() ne lève pas d'exception."""
    io = AudioIO()
    io._use_pulse = False

    def _boom(*a, **k):
        raise OSError("device indisponible")

    monkeypatch.setattr("hal_voice.adapters.audio_io.sd.play", _boom)
    data = np.zeros(100, dtype=np.int16)
    io._play_sounddevice(data, sample_rate=16000)  # ne doit pas lever


def test_play_pulse_ignores_paplay_error(monkeypatch, tmp_path) -> None:
    """Si paplay échoue, play() ne lève pas d'exception."""
    io = AudioIO()
    io._use_pulse = True
    io._pulse_output = "waveout"
    io._pulse_server = None

    def _raising_run(*a, **k):
        raise FileNotFoundError("paplay")

    monkeypatch.setattr("hal_voice.adapters.audio_io.subprocess.run", _raising_run)
    data = np.zeros(100, dtype=np.int16)
    io._play_pulse(data, sample_rate=16000)  # ne doit pas lever
