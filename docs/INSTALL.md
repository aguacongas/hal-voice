# Installation

> Guide d'installation de hal-voice sous **WSL2 / Linux**.
> L'app tourne dans WSL2 ; l'audio passe par PulseAudio for Windows
> (installé sur l'hôte).

## Voie rapide (recommandée) — setup.bat

Depuis l'hôte Windows, `scripts\setup.bat` fait tout :
1. Installe WSL2 + Ubuntu (si pas déjà fait, demande redémarrage)
2. Installe PulseAudio for Windows + configure `halvoice.pa` / `default.pa`
3. Configure un autostart pour PulseAudio
4. Lance `install.sh` dans WSL (venv + deps système + modèle Vosk)

```cmd
scripts\setup.bat
```

> Désinstallation : `scripts\teardown.bat` (safe) ou `scripts\teardown.bat --full`
> (supprime aussi WSL2 + Ubuntu).

## Installation manuelle (Linux / WSL2)

### 1. Dépendances système

```bash
sudo apt install espeak-ng pulseaudio-utils
```

(`libportaudio2` n'est plus nécessaire — le backend sounddevice a été retiré.)

### 2. Virtual Python + dépendances

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 3. Modèle Vosk FR (~40 Mo)

```bash
mkdir -p models && cd models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip
unzip vosk-model-small-fr-0.22.zip
rm vosk-model-small-fr-0.22.zip
```

Ou utilise ton script : `./scripts/install.sh` (auto-détection, multi-distro).

### Dépendances

| Package | Usage |
|---|---|
| `vosk` | Reconnaissance vocale offline (FR) |
| `pyttsx3` + `espeak-ng` | Synthèse vocale |
| `pulseaudio-utils` | `parecord`/`paplay` (audio WSL2) |
| `pynput` | Raccourcis clavier globaux |
| `soundfile` | Lecture/écriture WAV |

## Configuration PulseAudio (hôte Windows)

WSL2 ne voit pas le micro Windows par défaut. Il faut **PulseAudio for Windows**
(build pgaskin) exposant micro + haut-parleurs sur TCP 4713 :
- `module-waveout sink_name=waveout source_name=wavein record=1 input_device=<index>`
- `input_device` choisit le micro WaveIn (auto-détecté par le code)
- la ligne `module-waveout` de `default.pa` doit être **commentée** (évite un double device)

`scripts/setup.bat` gère tout ça automatiquement. Pour vérifier :

```bash
./scripts/run.sh --diagnose
```

## Tests

```bash
# Tous les tests
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
| `max_amplitude=0` (silence) | Vérifier `input_device` dans `halvoice.pa` |
| `Daemon already running` | Supprimer `%USERPROFILE%\.config\pulse\*-runtime\pid` |
| `Module Vosk introuvable` | Télécharger le modèle dans `models/` |
