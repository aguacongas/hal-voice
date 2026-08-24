"""
stt_vosk — Speech-to-Text offline via Vosk.

Charge un modèle Vosk (FR par défaut), accepte un buffer PCM int16 mono 16 kHz,
renvoie la transcription.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import Config, DEFAULT_SAMPLE_RATE

log = logging.getLogger(__name__)

# Vosk est bavard en logs, on coupe le bruit par défaut.
SetLogLevel(-1)


class STT:
    """Wrapper STT basé sur Vosk."""

    def __init__(self, config: Optional[Config] = None) -> None:
        cfg = config or Config.from_env()
        self._config = cfg
        self._model: Optional[Model] = None
        self._recognizer: Optional[KaldiRecognizer] = None
        self._loaded_path: Optional[Path] = None

    def load(self, model_path: Optional[Path | str] = None) -> None:
        """Charge le modèle Vosk (peut prendre 1-2 sec). Idempotent."""
        path = Path(model_path) if model_path else self._config.vosk_model_path
        if self._loaded_path == path:
            return
        if not path.exists():
            raise FileNotFoundError(
                f"Modèle Vosk introuvable : {path}\n"
                f"Télécharge-le depuis https://alphacephei.com/vosk/models "
                f"et place-le dans models/"
            )
        log.info("Chargement du modèle Vosk : %s", path)
        self._model = Model(str(path))
        self._recognizer = KaldiRecognizer(self._model, self._config.sample_rate)
        self._recognizer.SetWords(True)
        self._loaded_path = path

    def transcribe_array(self, audio: np.ndarray, sample_rate: Optional[int] = None) -> str:
        """Transcrit un buffer PCM complet (mono, int16 ou float)."""
        if self._recognizer is None:
            self.load()

        # Si sample_rate != config.sample_rate, on note pour le futur
        # (Vosk accepte de resampler en interne via mfcc.conf)
        if sample_rate is not None and sample_rate != self._config.sample_rate:
            log.debug(
                "sample_rate=%s != config.sample_rate=%s — Vosk va resampler",
                sample_rate,
                self._config.sample_rate,
            )

        # Conversion en bytes int16 little-endian (format attendu par Vosk)
        if audio.dtype != np.int16:
            audio_i16 = (audio * 32767).astype(np.int16)
        else:
            audio_i16 = audio.astype(np.int16, copy=False)

        # Stereo → mono
        if audio_i16.ndim > 1 and audio_i16.shape[1] > 1:
            audio_i16 = audio_i16.mean(axis=1).astype(np.int16)

        self._recognizer.AcceptWaveform(audio_i16.tobytes())
        result = json.loads(self._recognizer.FinalResult())
        return result.get("text", "").strip()

    def transcribe_file(self, path: Path | str) -> str:
        """Lit un WAV, transcrit. Sécurise le dtype pour Vosk."""
        import soundfile as sf  # local import pour éviter cycle
        data, sr = sf.read(str(path))
        return self.transcribe_array(data, sample_rate=sr)

    @property
    def model_path(self) -> Optional[Path]:
        return self._loaded_path


__all__ = ["STT", "DEFAULT_SAMPLE_RATE"]
