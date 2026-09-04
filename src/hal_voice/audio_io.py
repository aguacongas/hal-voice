"""Backward-compat : imports déplacés vers hal_voice.adapters.audio_io."""

from hal_voice.adapters.audio_io import (
    DEFAULT_CHANNELS,
    DEFAULT_DTYPE,
    DEFAULT_SAMPLE_RATE,
    AudioIO,
    pulse_diagnostics,
    quick_test,
)

__all__ = [
    "DEFAULT_CHANNELS",
    "DEFAULT_DTYPE",
    "DEFAULT_SAMPLE_RATE",
    "AudioIO",
    "pulse_diagnostics",
    "quick_test",
]

if __name__ == "__main__":
    quick_test()
