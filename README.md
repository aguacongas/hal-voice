# hal-voice

> Interface vocale 100% locale pour Windows et WSL2.
> **STT** (voix → texte) via [Vosk](https://alphacephei.com/vosk/) (offline, FR).
> **TTS** (texte → voix) via SAPI 5 (Windows) / pyttsx3+eSpeak (Linux).
> Pas de cloud, pas de clé d'API, pas d'écoute permanente.

## Objectif

Donner la parole et l'ouïe à un assistant vocal local, en français, sans dépendre d'un service cloud. Pensé pour un usage personnel : commandes vocales, relecture de textes, dictée.

## Fonctionnalités

| Mode | Description | Statut |
|---|---|---|
| **Commande vocale** | Phrase → intention → action (bonjour, stop, lis, au revoir) | v0.5.0 |
| **STT offline** | Transcription vocale via Vosk (FR, sans internet) | v0.3.0 |
| **TTS** | Synthèse vocale SAPI5 (Windows) / pyttsx3 (Linux) | v0.4.0 |
| **Audio I/O** | Capture micro + lecture audio (cross-platform) | v0.2.0 |
| **Hotkey global** | Raccourci clavier via pynput (F8, etc.) | v0.6.0 |
| **Wake word** | Détection du mot-clé "hal" | v0.6.0 |

## Stack technique

- **Langage** : Python 3.10+
- **STT** : [`vosk`](https://pypi.org/project/vosk/) + modèle `vosk-model-small-fr-0.22`
- **TTS** : SAPI 5 via `win32com` (Windows) / `pyttsx3` + `espeak-ng` (Linux)
- **Audio** : `sounddevice` (Windows) / `parecord`/`paplay` via PulseAudio (WSL2)
- **Hotkey** : `pynput` (cross-platform)
- **Config** : variables d'environnement (`HAL_VOICE_*`)

## Installation

### Windows

```cmd
git clone https://github.com/aguacongas/hal-voice.git
cd hal-voice
scripts\install.bat
```

### Linux / WSL2

```bash
git clone https://github.com/aguacongas/hal-voice.git
cd hal-voice
./scripts/install.sh
```

Voir [docs/INSTALL.md](docs/INSTALL.md) pour les détails.

## Utilisation

```bash
# Mode normal (boucle vocale)
python -m hal_voice
# ou
./scripts/run.sh          # Linux/WSL2
scripts\run.bat           # Windows

# Diagnostic PulseAudio (WSL2)
python -m hal_voice --diagnose

# Test audio rapide (record 3s + replay)
python -m hal_voice.audio_io
```

Voir [docs/USAGE.md](docs/USAGE.md) pour les commandes vocales.

## Structure

```
hal-voice/
├── src/hal_voice/          ← code source
│   ├── __main__.py         ← boucle principale
│   ├── audio_io.py         ← capture micro + playback
│   ├── stt_vosk.py         ← reconnaissance vocale (Vosk)
│   ├── tts_sapi.py         ← synthèse vocale (SAPI5/pyttsx3)
│   ├── commands.py         ← parser de commandes vocales
│   ├── config.py           ← configuration centralisée
│   ├── hotkey.py           ← raccourcis clavier (pynput)
│   └── wakeword.py         ← détection mot-clé (placeholder)
├── tests/                  ← tests unitaires (pytest)
├── scripts/                ← install + run (Windows/Linux/WSL2)
├── docs/                   ← architecture, install, usage, roadmap
├── models/                 ← modèle Vosk (gitignored)
├── requirements.txt
├── pyproject.toml
└── LICENSE                 ← Apache 2.0
```

## Tests

```bash
# Tous les tests
pytest

# Tests spécifiques
pytest tests/test_commands.py -v
pytest -m requires_hardware  # nécessite un micro
```

## Licence

**Apache License 2.0** — voir [LICENSE](LICENSE).

Les dépendances tierces ont leurs propres licences, listées dans [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES).

## Auteur

Olivier Lefebvre — [@aguacongas](https://github.com/aguacongas)
