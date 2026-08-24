"""Tests audio_io — sans dépendance matérielle.

Les tests qui capturent réellement le micro sont marqués `requires_hardware`.
"""

from __future__ import annotations

import pytest

from hal_voice.audio_io import (
    DEFAULT_CHANNELS,
    DEFAULT_DTYPE,
    DEFAULT_SAMPLE_RATE,
    AudioIO,
)


def test_default_constants() -> None:
    assert DEFAULT_SAMPLE_RATE == 16000
    assert DEFAULT_CHANNELS == 1
    assert DEFAULT_DTYPE == "int16"


def test_instantiation_uses_defaults() -> None:
    io = AudioIO()
    assert io.sample_rate == DEFAULT_SAMPLE_RATE
    assert io.channels == DEFAULT_CHANNELS
    assert io.dtype == DEFAULT_DTYPE


def test_instantiation_accepts_overrides() -> None:
    io = AudioIO(sample_rate=48000, channels=2, dtype="float32")
    assert io.sample_rate == 48000
    assert io.channels == 2
    assert io.dtype == "float32"


def test_list_devices_returns_list() -> None:
    io = AudioIO()
    devices = io.list_devices()
    # sounddevice renvoie un DeviceList (sequence-like), pas une vraie list
    assert len(devices) >= 1
    assert devices[0]["name"]
    assert "max_input_channels" in devices[0]


@pytest.mark.requires_hardware
def test_record_returns_correct_shape() -> None:
    io = AudioIO()
    audio = io.record(duration_seconds=0.5)
    assert audio.shape == (int(0.5 * DEFAULT_SAMPLE_RATE), 1)
    assert audio.dtype.name == "int16"
