"""
__main__.py — Point d'entrée principal de hal-voice.

Exécutable via ``python -m hal_voice``.
Utilise Clean Architecture : instancie les adapters, les injecte
dans l'Orchestrator (use case), et lance la boucle.

Modes :
    python -m hal_voice           → boucle vocale interactive
    python -m hal_voice --diagnose → diagnostic PulseAudio (WSL2)
    python -m hal_voice --silent  → boucle sans synthèse vocale (TTS muet)
"""

from __future__ import annotations

import logging
import sys

from hal_voice.adapters.audio_io import AudioIO, pulse_diagnostics
from hal_voice.adapters.config_loader import load_config_from_env
from hal_voice.adapters.stt_vosk import STT
from hal_voice.adapters.tts import TTS
from hal_voice.use_cases.command_parser import CommandParser
from hal_voice.use_cases.orchestrator import Orchestrator
from hal_voice.use_cases.wakeword import WakeWordDetector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    """Point d'entrée principal. Retourne 0 si OK, 1 si erreur."""

    if "--diagnose" in sys.argv:
        pulse_diagnostics()
        return 0

    cfg = load_config_from_env()

    # Injection des adapters dans les use cases
    io = AudioIO(sample_rate=cfg.sample_rate)
    stt = STT(model_path=cfg.vosk_model_path, sample_rate=cfg.sample_rate)
    tts = TTS()
    parser = CommandParser()

    log.info("Hal s'éveille... (v0.5.0)")

    orchestrator = Orchestrator(
        capture=io,
        stt=stt,
        tts=tts,
        parser=parser,
        silent=cfg.silent,
        wake_detector=WakeWordDetector(cfg.wake_word),
    )
    return orchestrator.run()


if __name__ == "__main__":
    sys.exit(main())
