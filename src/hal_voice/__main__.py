"""
__main__.py — Point d'entrée principal de hal-voice.

Exécutable via ``python -m hal_voice``.
Boucle principale : capture 3s → transcription → parsing → exécution → TTS.

Modes :
    python -m hal_voice           → boucle vocale interactive
    python -m hal_voice --diagnose → diagnostic PulseAudio (WSL2)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

from .audio_io import AudioIO, pulse_diagnostics
from .commands import CommandParser
from .config import Config
from .stt_vosk import STT
from .tts_sapi import TTS

# Configuration du logging : affiche les messages INFO et plus.
# Format simple : "NIVEAU: message" sans timestamp (suffisant pour un assistant local).
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    """Point d'entrée principal. Retourne 0 si OK, 1 si erreur."""

    # ── Mode diagnostic ───────────────────────────────────────────────
    # Affiche les infos PulseAudio (serveur, sources, test de capture)
    # puis quitte. Utile pour dépanner les problèmes de micro sous WSL2.
    if "--diagnose" in sys.argv:
        pulse_diagnostics()
        return 0

    # ── Initialisation des composants ─────────────────────────────────
    cfg = Config.from_env()

    # AudioIO : capture micro + playback. Détecte automatiquement
    # sounddevice (Windows) ou PulseAudio (WSL2).
    io = AudioIO(sample_rate=cfg.sample_rate)
    # STT : reconnaissance vocale offline via Vosk (modèle FR small)
    stt = STT(config=cfg)
    # TTS : synthèse vocale. SAPI5 sur Windows, pyttsx3+eSpeak sur Linux.
    tts = TTS()
    # CommandParser : analyse le texte transcrit pour extraire une intention
    parser = CommandParser()

    log.info("Hal s'éveille... (v0.5.0)")
    tts.speak("Systèmes opérationnels. Je vous écoute.")

    # ── Boucle principale ─────────────────────────────────────────────
    # Chaque itération :
    #   1. Capture 3 secondes d'audio
    #   2. Transcrit en texte (Vosk)
    #   3. Parse le texte pour extraire une intention
    #   4. Exécute l'action correspondante
    #   5. Répond par TTS
    try:
        while True:
            print("\n--- En attente d'une commande (3s) ---")

            # Capture audio pendant 3 secondes
            # Retourne un numpy array int16 mono (48000 échantillons)
            audio = io.record(duration_seconds=3.0)
            max_amp = int(np.abs(audio).max())
            log.info("Audio capturé : shape=%s max_amplitude=%d", audio.shape, max_amp)

            # Transcription du buffer audio en texte (Vosk, offline)
            # Retourne une chaîne vide si rien n'a été détecté
            text = stt.transcribe_array(audio)
            if not text:
                continue

            print(f"Vous : {text}")

            # Analyse du texte pour extraire une intention + paramètres
            # Ex: "lis notes.txt" → Intent(name="READ_FILE", params={"filename": "notes.txt"})
            intent = parser.parse(text)
            if not intent:
                continue

            print(f"Hal [Intent] : {intent.name} {intent.params}")

            # ── Exécution des intentions ──────────────────────────────
            if intent.name == "GREETING":
                tts.speak("Bonjour Olivier. Que puis-je faire pour vous ?")

            elif intent.name == "STOP":
                # Coupe la parole en cours (utile si TTS parle encore)
                tts.stop()
                tts.speak("Silence immédiat.")

            elif intent.name == "READ_FILE":
                # Lit le contenu d'un fichier et le prononce
                filename = intent.params.get("filename")
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
        # Ctrl+C → arrêt propre
        log.info("Arrêt demandé par l'utilisateur.")
    except Exception:
        # Erreur inattendue → log complète puis code 1
        log.exception("Erreur critique durant la boucle principale")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
