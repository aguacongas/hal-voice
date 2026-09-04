"""
stt_vosk — Speech-to-Text offline via Vosk.

Charge un modèle Vosk (FR par défaut), accepte un buffer PCM int16 mono 16 kHz,
renvoie la transcription en texte.

Vosk est un moteur STT offline basé sur Kaldi. Il fonctionne sans connexion
internet et supporte plusieurs langues. Le modèle small FR (~40 Mo) est
suffisant pour des commandes vocales simples.

Utilisation ::
    stt = STT()
    texte = stt.transcribe_array(buffer_audio)  # → "bonjour hal"
    texte = stt.transcribe_file("recording.wav")  # → "lis le fichier"

Format d'entrée attendu :
    - numpy array int16, mono, 16 kHz
    - Si float, sera converti en int16 (×32767)
    - Si stereo, sera converti en mono (moyenne des canaux)

Pièges :
    - Le modèle doit être téléchargé séparément (pas inclus dans le repo)
    - Le chargement prend 1-2 secondes
    - Vosk est bavard en logs → on coupe le niveau à -1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import DEFAULT_SAMPLE_RATE, Config

log = logging.getLogger(__name__)

# Vosk est très bavard en logs (Kaldi est verbeux par défaut).
# SetLogLevel(-1) coupe tous les messages sauf les erreurs critiques.
SetLogLevel(-1)


class STT:
    """Wrapper STT basé sur Vosk.

    Le modèle est chargé de manière lazy (au premier appel de
    ``transcribe_array`` si ``load()`` n'a pas été appelé).
    """

    def __init__(self, config: Config | None = None) -> None:
        cfg = config or Config.from_env()
        self._config = cfg
        # Modèle Vosk et recogniseur — chargés à la demande
        self._model: Model | None = None
        self._recognizer: KaldiRecognizer | None = None
        # Chemin du modèle chargé (pour vérifier l'idempotence)
        self._loaded_path: Path | None = None

    def load(self, model_path: Path | str | None = None) -> None:
        """Charge le modèle Vosk (peut prendre 1-2 sec).

        Idempotent : si le même chemin est déjà chargé, ne fait rien.
        Lève FileNotFoundError si le chemin n'existe pas.
        """
        path = Path(model_path) if model_path else self._config.vosk_model_path
        # Vérifie si déjà chargé
        if self._loaded_path == path:
            return
        if not path.exists():
            raise FileNotFoundError(
                f"Modèle Vosk introuvable : {path}\n"
                f"Télécharge-le depuis https://alphacephei.com/vosk/models "
                f"et place-le dans models/"
            )
        log.info("Chargement du modèle Vosk : %s", path)
        # Model() charge le modèle en mémoire (1-2s)
        self._model = Model(str(path))
        # KaldiRecognizer gère la reconnaissance de parole
        self._recognizer = KaldiRecognizer(self._model, self._config.sample_rate)
        # SetWords(True) active les timestamps par mot (pour le futur)
        self._recognizer.SetWords(True)
        self._loaded_path = path

    def transcribe_array(self, audio: np.ndarray, sample_rate: int | None = None) -> str:
        """Transcrit un buffer PCM complet (mono, int16 ou float).

        Auto-charge le modèle si load() n'a pas été appelé.
        Gère la conversion de format (float→int16, stereo→mono).

        Args:
            audio: Buffer numpy (int16 ou float, mono ou stereo)
            sample_rate: Si différent de config, Vosk resamplera en interne

        Returns:
            Texte transcrit, ou chaîne vide si rien détecté
        """
        # Lazy loading du modèle si nécessaire
        if self._recognizer is None:
            self.load()

        # Log si le sample_rate diffère de la config
        # (Vosk peut resampler via mfcc.conf, mais c'est plus lent)
        if sample_rate is not None and sample_rate != self._config.sample_rate:
            log.debug(
                "sample_rate=%s != config.sample_rate=%s — Vosk va resampler",
                sample_rate,
                self._config.sample_rate,
            )

        # Conversion en int16 little-endian (format natif de Vosk)
        # Si l'audio est en float [-1, 1], on multiplie par 32767
        if audio.dtype != np.int16:
            audio_i16 = (audio * 32767).astype(np.int16)
        else:
            audio_i16 = audio.astype(np.int16, copy=False)

        # Conversion stereo → mono par moyennage des canaux
        if audio_i16.ndim > 1 and audio_i16.shape[1] > 1:
            audio_i16 = audio_i16.mean(axis=1).astype(np.int16)

        # Envoie le buffer au recogniseur et récupère le résultat
        self._recognizer.AcceptWaveform(audio_i16.tobytes())
        result = json.loads(self._recognizer.FinalResult())
        return result.get("text", "").strip()

    def transcribe_file(self, path: Path | str) -> str:
        """Lit un fichier WAV, transcrit. Sécurise le dtype pour Vosk.

        Utilise soundfile pour lire le fichier (supporte WAV, FLAC, OGG).
        La conversion en int16 est gérée par transcribe_array.
        """
        import soundfile as sf  # import local pour éviter un cycle d'imports
        data, sr = sf.read(str(path))
        return self.transcribe_array(data, sample_rate=sr)

    @property
    def model_path(self) -> Path | None:
        """Chemin du modèle actuellement chargé (None si pas encore chargé)."""
        return self._loaded_path


__all__ = ["DEFAULT_SAMPLE_RATE", "STT"]
