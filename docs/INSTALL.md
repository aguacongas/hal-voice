# Installation

> Guide d'installation de hal-voice sur Windows et Linux/WSL2.

## Prérequis

- Python 3.10+ installé et dans le PATH
- Connexion internet (pour le téléchargement du modèle Vosk)
- Git

## Windows

### Installation rapide

```cmd
git clone https://github.com/aguacongas/hal-voice.git
cd hal-voice
scripts\install.bat
```

### Installation manuelle

```cmd
# Créer le venv
python -m venv .venv
.venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt
pip install -e .

# Télécharger le modèle Vosk FR (~40 Mo)
mkdir models
cd models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip
tar -xf vosk-model-small-fr-0.22.zip
del vosk-model-small-fr-0.22.zip
```

### Dépendances Windows

| Package | Usage |
|---|---|
| `sounddevice` | Capture micro (PortAudio) |
| `vosk` | Reconnaissance vocale offline |
| `pywin32` | TTS via SAPI 5 |
| `pynput` | Raccourcis clavier globaux |
| `pyttsx3` | TTS alternatif (Linux) |
| `soundfile` | Lecture/écriture WAV |

### Vérification

```cmd
python -m hal_voice --diagnose
```

## Linux / WSL2

### Installation rapide

```bash
git clone https://github.com/aguacongas/hal-voice.git
cd hal-voice
./scripts/install.sh
```

### Installation manuelle

```bash
# Dépendances système
sudo apt install libportaudio2 espeak-ng pulseaudio-utils

# Créer le venv
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
pip install -e .

# Télécharger le modèle Vosk FR
mkdir -p models && cd models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip
unzip vosk-model-small-fr-0.22.zip
rm vosk-model-small-fr-0.22.zip
```

### Dépendances Linux

| Package | Usage |
|---|---|
| `libportaudio2` | Backend audio pour sounddevice |
| `espeak-ng` | Moteur TTS pour pyttsx3 |
| `pulseaudio-utils` | `parecord`/`paplay` pour WSL2 |

### Configuration PulseAudio (WSL2)

WSL2 ne voit pas le micro Windows par défaut. Il faut **PulseAudio for Windows** :

1. Télécharger [PulseAudio for Windows](https://github.com/pgaskin/pulseaudio-win32)
2. Configurer `halvoice.pa` avec le bon `input_device` (utiliser `scripts/detect-mic.ps1`)
3. Le script `run.sh` démarre PulseAudio automatiquement si nécessaire

Voir [ARCHITECTURE.md](ARCHITECTURE.md) pour les détails techniques.

### Vérification

```bash
./scripts/run.sh --diagnose
```

## Tests

```bash
# Tous les tests (32+ passent)
pytest

# Tests spécifiques
pytest tests/test_commands.py -v

# Tests nécessitant un micro
pytest -m requires_hardware
```

## Dépannage

| Problème | Solution |
|---|---|
| `parecord: command not found` | `sudo apt install pulseaudio-utils` |
| `PulseAudio Windows non trouvé` | Vérifier que PulseAudio tourne sur Windows (port 4713) |
| `max_amplitude=0` (silence) | Vérifier `input_device` dans `halvoice.pa`, lancer `detect-mic.ps1` |
| `Daemon already running` | Supprimer `%USERPROFILE%\.config\pulse\*-runtime\pid` |
| `Module Vosk introuvable` | Télécharger le modèle dans `models/` |
