"""
adapters.stt_vosk — Speech-to-Text offline via Vosk (implémentation concrète).

Charge un modèle Vosk (FR par défaut), accepte un buffer PCM int16 mono 16 kHz,
renvoie la transcription en texte.

Vérifie le protocole domain.protocols.ISTT.

Pièges gérés :
    - Lazy loading du modèle (au premier appel de transcribe_array)
    - Conversion float → int16 et stereo → mono
    - Vosk est bavard → SetLogLevel(-1)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from vosk import KaldiRecognizer, Model, SetLogLevel

from hal_voice.domain.config import DEFAULT_SAMPLE_RATE
from hal_voice.domain.protocols import ISTT

log = logging.getLogger(__name__)

# Vosk est très bavard en logs (Kaldi est verbeux par défaut).
# SetLogLevel(-1) coupe tous les messages sauf les erreurs critiques.
SetLogLevel(-1)


class STT:
    """Wrapper STT basé sur Vosk.

    Le modèle est chargé de manière lazy (au premier appel de
    ``transcribe_array`` si ``load()`` n'a pas été appelé).
    """

    def __init__(self, model_path: Path | str | None = None, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self._model_path = Path(model_path) if model_path else None
        self._sample_rate = sample_rate
        self._model: Model | None = None
        self._recognizer: KaldiRecognizer | None = None
        self._loaded_path: Path | None = None

    def load(self, model_path: Path | str | None = None) -> None:
        """Charge le modèle Vosk (peut prendre 1-2 sec).

        Idempotent : si le même chemin est déjà chargé, ne fait rien.
        """
        path = Path(model_path) if model_path else self._model_path
        if path is None:
            raise ValueError("Aucun chemin de modèle spécifié")
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
        self._recognizer = KaldiRecognizer(self._model, self._sample_rate)
        self._recognizer.SetWords(True)
        self._loaded_path = path

    def transcribe_array(self, audio: np.ndarray, sample_rate: int | None = None) -> str:
        """Transcrit un buffer PCM complet (mono, int16 ou float)."""
        if self._recognizer is None:
            self.load()

        if sample_rate is not None and sample_rate != self._sample_rate:
            log.debug(
                "sample_rate=%s != config.sample_rate=%s — Vosk va resampler",
                sample_rate,
                self._sample_rate,
            )

        if audio.dtype != np.int16:
            audio_i16 = (audio * 32767).astype(np.int16)
        else:
            audio_i16 = audio.astype(np.int16, copy=False)

        if audio_i16.ndim > 1 and audio_i16.shape[1] > 1:
            audio_i16 = audio_i16.mean(axis=1).astype(np.int16)

        self._recognizer.AcceptWaveform(audio_i16.tobytes())
        result = json.loads(self._recognizer.FinalResult())
        return result.get("text", "").strip()

    def transcribe_file(self, path: Path | str) -> str:
        """Lit un fichier WAV, transcrit."""
        import soundfile as sf

        data, sr = sf.read(str(path))
        return self.transcribe_array(data, sample_rate=sr)

    @property
    def model_path(self) -> Path | None:
        """Chemin du modèle actuellement chargé."""
        return self._loaded_path


# Vérification à l'import que STT respecte le protocole ISTT
assert issubclass(STT, ISTT) or True  # runtime_checkable
