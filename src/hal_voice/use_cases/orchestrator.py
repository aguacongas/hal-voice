"""
use_cases.orchestrator — Boucle principale de hal-voice.

Coordonne les use cases : capture audio → STT → parsing → exécution → TTS.
Ne dépend que des protocoles (domain.protocols), pas des adapters concrets.

Architecture :
    Orchestrator.run() lance la boucle interactive.
    Orchestrator.execute_intent() dispatche vers le handler approprié.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from hal_voice.domain.entities import Intent
from hal_voice.domain.protocols import ISTT, ITTS, IAudioCapture
from hal_voice.use_cases.command_parser import CommandParser

log = logging.getLogger(__name__)


class Orchestrator:
    """Boucle principale : capture → STT → parsing → exécution → TTS.

    Reçoit les adapters via injection de dépendances (protocoles).
    """

    def __init__(
        self,
        capture: IAudioCapture,
        stt: ISTT,
        tts: ITTS,
        parser: CommandParser,
    ) -> None:
        self._capture = capture
        self._stt = stt
        self._tts = tts
        self._parser = parser

    def run(self) -> int:
        """Lance la boucle vocale interactive. Retourne 0 si OK."""
        self._tts.speak("Systèmes opérationnels. Je vous écoute.")
        try:
            while True:
                print("\n--- En attente d'une commande (3s) ---")

                audio = self._capture.record(duration_seconds=3.0)
                max_amp = int(np.abs(audio).max())
                log.info("Audio capturé : shape=%s max_amplitude=%d", audio.shape, max_amp)

                text = self._stt.transcribe_array(audio)
                if not text:
                    continue

                print(f"Vous : {text}")

                intent = self._parser.parse(text)
                if not intent:
                    continue

                print(f"Hal [Intent] : {intent.name} {intent.params}")

                if self.execute_intent(intent):
                    break

        except KeyboardInterrupt:
            log.info("Arrêt demandé par l'utilisateur.")
        except Exception:
            log.exception("Erreur critique durant la boucle principale")
            return 1

        return 0

    def execute_intent(self, intent: Intent) -> bool:
        """Exécute une intention. Retourne True s'il faut quitter la boucle."""
        if intent.name == "GREETING":
            self._tts.speak("Bonjour Olivier. Que puis-je faire pour vous ?")

        elif intent.name == "STOP":
            self._tts.stop()
            self._tts.speak("Silence immédiat.")

        elif intent.name == "READ_FILE":
            filename = intent.params.get("filename")
            path = Path(filename) if filename else None
            if path and path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8")
                self._tts.speak(f"Lecture de {filename}. {content}")
            else:
                self._tts.speak(f"Je ne trouve pas le fichier {filename}.")

        elif intent.name == "EXIT":
            self._tts.speak("Au revoir.")
            return True

        elif intent.name == "ERROR":
            msg = intent.params.get("msg", "Une erreur est survenue.")
            self._tts.speak(msg)

        return False
