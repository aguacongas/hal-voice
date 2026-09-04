"""
Tests audio_io — sans dépendance matérielle pour les tests unitaires.

Les tests qui capturent réellement le micro sont marqués ``requires_hardware``
et ne sont joués que sur les machines avec une carte son active.

Marqueurs pytest utilisés :
    - requires_hardware : nécessite un micro fonctionnel
    - requires_windows  : spécifique à Windows (SAPI 5, PortAudio)
"""

from __future__ import annotations

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
