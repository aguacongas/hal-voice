# hal-voice

> Interface vocale 100% locale pour **WSL2 / Linux**.
> **STT** (voix → texte) via [Vosk](https://alphacephei.com/vosk/) (offline, FR).
> **TTS** (texte → voix) via pyttsx3 + eSpeak-ng.
> Pas de cloud, pas de clé d'API, pas d'écoute permanente.

## Objectif

Donner la parole et l'ouïe à un assistant vocal local, en français, sans dépendre d'un service cloud. Pensé pour un usage personnel : commandes vocales, relecture de textes, dictée.

> L'app tourne sous **WSL2**. Le micro et les haut-parleurs passent par un serveur
> PulseAudio installé sur l'hôte Windows (TCP 4713). Le support natif Windows
> (SAPI 5, sounddevice) a été retiré.

## Fonctionnalités

| Mode | Description | Statut |
|---|---|---|
| **Commande vocale** | Phrase → intention → action (bonjour, stop, lis, au revoir) | v0.5.0 |
| **STT offline** | Transcription vocale via Vosk (FR, sans internet) | v0.3.0 |
| **TTS** | Synthèse vocale pyttsx3 + eSpeak-ng (voix FR France) | v0.4.0 |
| **Audio I/O** | Capture micro + lecture via PulseAudio (parecord/paplay) | v0.2.0 |
| **Hotkey global** | Raccourci clavier via pynput (F8, etc.) | v0.6.0 |
| **Wake word** | Détection du mot-clé "hal" | v0.6.0 |

## Stack technique (Clean Architecture)

- **Langage** : Python 3.10+
- **STT** : [`vosk`](https://pypi.org/project/vosk/) + modèle `vosk-model-small-fr-0.22`
- **TTS** : `pyttsx3` + `espeak-ng`
- **Audio** : `parecord`/`paplay` via PulseAudio (WSL2)
- **Hotkey** : `pynput`
- **Config** : variables d'environnement (`HAL_VOICE_*`)
- **Structure** : `domain/` (protocoles/entités) · `use_cases/` (logique métier) · `adapters/` (implémentations)

## Installation

### WSL2 (recommandé)

```cmd
scripts\setup.bat          REM installe WSL2 + Ubuntu + PulseAudio + deps (depuis l'hôte Windows)
```

### Linux / WSL2 (manuel)

```bash
git clone https://github.com/aguacongas/hal-voice.git
cd hal-voice
./scripts/install.sh       # auto-install Python + deps système + venv + modèle Vosk
```

Voir [docs/INSTALL.md](docs/INSTALL.md) pour les détails.

## Utilisation

```bash
# Mode normal (boucle vocale)
./scripts/run.sh                    # WSL2/Linux

# Diagnostic PulseAudio (WSL2)
./scripts/run.sh --diagnose

# Test audio rapide (record 3s + replay)
python -m hal_voice.audio_io

# Mode silencieux (test STT sans synthèse vocale)
./scripts/run.sh --silent
```

Voir [docs/USAGE.md](docs/USAGE.md) pour les commandes vocales.

## Structure

```
hal-voice/
├── src/hal_voice/
│   ├── __main__.py        ← point d'entrée (DI : injecte les adapters)
│   ├── domain/            ← entities, protocols, config (cœur pur)
│   ├── use_cases/         ← command_parser, orchestrator (logique métier)
│   └── adapters/          ← audio_io, stt_vosk, tts, config_loader, hotkey
├── tests/                 ← tests unitaires + end-to-end (pytest)
├── scripts/               ← install/uninstall/setup/teardown/run
├── docs/                  ← architecture, install, usage, roadmap
├── models/                ← modèle Vosk (gitignored)
├── requirements.txt
├── pyproject.toml
└── LICENSE                ← Apache 2.0
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
