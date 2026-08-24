"""
audio_io — capture micro + lecture audio.

Cœur du module, isolé de PortAudio via sounddevice. Aucune dépendance Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

DEFAULT_SAMPLE_RATE = 16_000  # 16 kHz, standard pour STT (Vosk, Whisper...)
DEFAULT_CHANNELS = 1           # mono
DEFAULT_DTYPE = "int16"        # 16 bits, attendu par Vosk


class AudioIO:
    """Helper pour capturer et lire de l'audio en PCM."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        dtype: str = DEFAULT_DTYPE,
        input_device: Optional[int | str] = None,
        output_device: Optional[int | str] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.input_device = input_device
        self.output_device = output_device

    def list_devices(self) -> list[dict]:
        """Retourne la liste des devices audio détectés."""
        return sd.query_devices()  # type: ignore[return-value]

    def default_input_name(self) -> str:
        return sd.query_devices(kind="input")["name"]  # type: ignore[index]

    def default_output_name(self) -> str:
        return sd.query_devices(kind="output")["name"]  # type: ignore[index]

    def record(self, duration_seconds: float) -> np.ndarray:
        """Capture `duration_seconds` du micro et renvoie un numpy array.

        Bloquant : attend la fin de la capture.
        """
        frames = int(duration_seconds * self.sample_rate)
        audio = sd.rec(
            frames,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            device=self.input_device,
        )
        sd.wait()
        return np.asarray(audio)

    def play(self, audio: np.ndarray, sample_rate: Optional[int] = None) -> None:
        """Joue un buffer audio. Bloquant : attend la fin de la lecture."""
        sr = sample_rate or self.sample_rate
        sd.play(
            audio,
            samplerate=sr,
            device=self.output_device,
            blocking=True,
        )

    def record_to_file(self, path: str | Path, duration_seconds: float) -> Path:
        """Capture et écrit directement dans un fichier WAV."""
        audio = self.record(duration_seconds)
        out = Path(path)
        sf.write(out, audio, self.sample_rate)
        return out

    def play_file(self, path: str | Path) -> None:
        """Lit un fichier WAV (ou tout format supporté par libsndfile)."""
        data, sr = sf.read(str(path))
        if data.ndim > 1 and self.channels == 1:
            data = data.mean(axis=1)
        # Assure le dtype attendu par la carte son
        if data.dtype != self.dtype and self.dtype == "int16":
            data = (data * 32767).astype("int16")
        self.play(np.asarray(data), sample_rate=sr)


def quick_test() -> None:
    """Boucle 5s : record 3s, replay, affiche devices. Pour test manuel."""
    io = AudioIO()
    print(f"Input par défaut : {io.default_input_name()}")
    print(f"Output par défaut : {io.default_output_name()}")
    print("Capture 3 sec...")
    audio = io.record(3.0)
    print(f"Capturé : {audio.shape}, dtype={audio.dtype}")
    print("Replay...")
    io.play(audio)
    print("Fin.")


if __name__ == "__main__":
    quick_test()
