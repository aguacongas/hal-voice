"""Entry point: `python -m hal_voice`."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .audio_io import AudioIO
from .commands import CommandParser
from .config import Config
from .stt_vosk import STT
from .tts_sapi import TTS

# Setup minimal logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    cfg = Config.from_env()
    
    # Initialisation des composants
    io = AudioIO(sample_rate=cfg.sample_rate)
    stt = STT(config=cfg)
    tts = TTS()
    parser = CommandParser()

    log.info("Hal s'éveille... (v0.5.0)")
    tts.speak("Systèmes opérationnels. Je vous écoute.")

    try:
        while True:
            print("\n--- En attente d'une commande (3s) ---")
            # Capture un segment court
            audio = io.record(duration_seconds=3.0)
            
            # Transcription
            text = stt.transcribe_array(audio)
            if not text:
                continue

            print(f"Vous : {text}")

            # Analyse de l'intention
            intent = parser.parse(text)
            if not intent:
                # On peut ignorer ou répondre qu'on n'a pas compris
                continue

            print(f"Hal [Intent] : {intent.name} {intent.params}")

            # Exécution de l'intention
            if intent.name == "GREETING":
                tts.speak("Bonjour Olivier. Que puis-je faire pour vous ?")

            elif intent.name == "STOP":
                tts.stop()
                tts.speak("Silence immédiat.")

            elif intent.name == "READ_FILE":
                filename = intent.params.get("filename")
                # On cherche le fichier dans le dossier courant ou un chemin spécifié
                path = Path(filename)
                if path.exists() and path.is_file():
                    content = path.read_text(encoding="utf-8")
                    tts.speak(f"Lecture de {filename}. {content}")
                else:
                    tts.speak(f"Je ne trouve pas le fichier {filename}.")

            elif intent.name == "EXIT":
                tts.speak("Au revoir.")
                break

            elif intent.name == "ERROR":
                msg = intent.params.get("msg", "Une erreur est survenue.")
                tts.speak(msg)

    except KeyboardInterrupt:
        log.info("Arrêt demandé par l'utilisateur.")
    except Exception:
        log.exception("Erreur critique durant la boucle principale")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
