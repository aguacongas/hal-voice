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
from hal_voice.use_cases.wakeword import AdaptiveVoiceActivity, WakeWordDetector

log = logging.getLogger(__name__)


class Orchestrator:
    """Boucle principale : capture → STT → parsing → exécution → TTS.

    Reçoit les adapters via injection de dépendances (protocoles).

    Deux modes d'écoute :
        - ``wake_detector=None`` (défaut) : écoute continue, chaque
          tranche de 3 s est transcrite et traitée.
        - ``wake_detector`` fourni : **mode veille** — écoute basse
          consommation via un VAD adaptatif, ne transcrit que quand on
          parle, et ne s'engage (écoute de la commande) qu'après avoir
          entendu le mot d'activation ("hal").
    """

    def __init__(
        self,
        capture: IAudioCapture,
        stt: ISTT,
        tts: ITTS,
        parser: CommandParser,
        silent: bool = False,
        wake_detector: WakeWordDetector | None = None,
        vad: AdaptiveVoiceActivity | None = None,
        slice_seconds: float = 1.0,
        engage_seconds: float = 3.0,
    ) -> None:
        self._capture = capture
        self._stt = stt
        self._tts = tts
        self._parser = parser
        self._silent = silent
        self._wake_detector = wake_detector
        self._vad = vad
        self._slice_seconds = slice_seconds
        self._engage_seconds = engage_seconds
        self._engaged_exit = False

    def _speak(self, text: str) -> None:
        """Prononce ``text``, sauf en mode silencieux (``--silent``)."""
        if not self._silent:
            self._tts.speak(text)

    def run(self) -> int:
        """Lance la boucle vocale interactive. Retourne 0 si OK."""
        self._speak("Systèmes opérationnels. Je vous écoute.")
        try:
            if self._wake_detector is None:
                self._run_continuous()
            else:
                self._run_standby()

        except KeyboardInterrupt:
            log.info("Arrêt demandé par l'utilisateur.")
        except Exception:
            log.exception("Erreur critique durant la boucle principale")
            return 1

        return 0

    def _run_continuous(self) -> None:
        """Mode écoute continue : on transcrit chaque tranche de 3 s."""
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

    def _run_standby(self) -> None:
        """Mode veille : écoute courte, ne transcrit que si on parle, ne
        s'engage qu'après le mot d'activation."""
        assert self._wake_detector is not None
        vad = self._vad or AdaptiveVoiceActivity()

        while True:
            # 1. Tranche courte "basse consommation" pour le VAD.
            audio = self._capture.record(duration_seconds=self._slice_seconds)
            max_amp = int(np.abs(audio).max())
            speech = vad.update(max_amp)

            if not speech:
                # Silence : on reste en veille sans transcrire (économie).
                continue

            # 2. On entend quelque chose : on transcrit pour chercher le wake word.
            text = self._stt.transcribe_array(audio)
            log.info("Parole détectée (amp=%d) → %r", max_amp, text)
            if not text:
                continue

            print(f"Vous : {text}")

            if not self._wake_detector.matches(text):
                # Parole mais pas le mot d'activation → on reste en veille.
                print("(pas le mot d'activation)")
                continue

            # 3. Wake word entendu → on s'engage pour écouter la commande.
            self._speak("Bonjour. Je vous écoute.")
            self._listen_engaged()
            if self._engaged_exit:
                return

    def _listen_engaged(self) -> None:
        """Après le wake word, on écoute la commande sur une fenêtre plus longue."""
        self._engaged_exit = False
        print("\n--- Commande (après wake word) ---")
        audio = self._capture.record(duration_seconds=self._engage_seconds)
        text = self._stt.transcribe_array(audio)
        if not text:
            return

        print(f"Vous : {text}")

        intent = self._parser.parse(text)
        if not intent:
            return

        print(f"Hal [Intent] : {intent.name} {intent.params}")
        if self.execute_intent(intent):
            self._engaged_exit = True

    def execute_intent(self, intent: Intent) -> bool:
        """Exécute une intention. Retourne True s'il faut quitter la boucle."""
        if intent.name == "GREETING":
            self._speak("Bonjour Olivier. Que puis-je faire pour vous ?")

        elif intent.name == "STOP":
            self._tts.stop()
            self._speak("Silence immédiat.")

        elif intent.name == "READ_FILE":
            filename = intent.params.get("filename")
            path = Path(filename) if filename else None
            if path and path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8")
                self._speak(f"Lecture de {filename}. {content}")
            else:
                self._speak(f"Je ne trouve pas le fichier {filename}.")

        elif intent.name == "EXIT":
            self._speak("Au revoir.")
            return True

        elif intent.name == "ERROR":
            msg = intent.params.get("msg", "Une erreur est survenue.")
            self._speak(msg)

        return False
