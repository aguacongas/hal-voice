"""
adapters.audio_io — Capture micro + lecture audio (implémentation concrète).

Vérifie les protocoles IAudioCapture et IAudioPlayback.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from hal_voice.domain.config import DEFAULT_CHANNELS, DEFAULT_DTYPE, DEFAULT_SAMPLE_RATE

log = logging.getLogger(__name__)


class AudioIO:
    """Helper pour capturer et lire de l'audio en PCM via sounddevice."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        dtype: str = DEFAULT_DTYPE,
        input_device: int | str | None = None,
        output_device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.input_device = input_device
        self.output_device = output_device

        # Utilisation des devices par défaut si aucun n'est spécifié
        self._input_id = (
            self.input_device if self.input_device is not None else sd.default.device[0]
        )
        self._output_id = (
            self.output_device if self.output_device is not None else sd.default.device[1]
        )

        log.info("AudioIO initialisé : input=%s, output=%s", self._input_id, self._output_id)

    def list_devices(self) -> list[dict]:
        """Retourne la liste des devices audio détectés."""
        devices = sd.query_devices()
        return [{"index": i, "name": d["name"]} for i, d in enumerate(devices)]

    def default_input_name(self) -> str:
        """Retourne le nom du device d'entrée par défaut."""
        try:
            return sd.query_devices(self._input_id)["name"]
        except Exception:
            return "unknown"

    def default_output_name(self) -> str:
        """Retourne le nom du device de sortie par défaut."""
        try:
            return sd.query_devices(self._output_id)["name"]
        except Exception:
            return "unknown"

    # ── Capture ──────────────────────────────────────────────────────

    def record(self, duration_seconds: float) -> np.ndarray:
        """Capture ``duration_seconds`` du micro et renvoie un numpy array int16 mono."""
        try:
            recording = sd.rec(
                int(duration_seconds * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                device=self._input_id,
            )
            sd.wait()
            return recording.reshape(-1, 1)
        except Exception:
            log.exception("Erreur lors de la capture audio")
            return np.zeros((int(duration_seconds * self.sample_rate), 1), dtype=np.int16)

    # ── Lecture ──────────────────────────────────────────────────────

    def play(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Joue un buffer audio. Bloquant jusqu'à la fin de la lecture."""
        sr = sample_rate or self.sample_rate
        try:
            sd.play(audio, samplerate=sr, device=self._output_id)
            sd.wait()
        except Exception:
            log.exception("Erreur lors de la lecture audio")

    # ── Fichiers ────────────────────────────────────────────────────

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
        if data.dtype != self.dtype and self.dtype == "int16":
            data = (data * 32767).astype("int16")
        self.play(np.asarray(data), sample_rate=sr)


def quick_test() -> None:
    """Boucle 5s : record 3s, replay, affiche devices. Pour test manuel."""
    io = AudioIO()
    print("Backend : sounddevice (Windows)")
    print(f"Input device  : {io.default_input_name()}")
    print(f"Output device : {io.default_output_name()}")
    print("Capture 3 sec...")
    audio = io.record(3.0)
    max_amp = int(np.abs(audio).max())
    print(f"Capturé : {audio.shape}, max amplitude = {max_amp}")
    if max_amp < 100:
        print("⚠ Aucun son capté — vérifie ton micro")
    else:
        print("Replay...")
        io.play(audio)
    print("Fin.")


if __name__ == "__main__":
    quick_test()
