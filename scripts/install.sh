#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# install.sh — Installeur hal-voice pour Linux / WSL2
#
# Ce script :
#   1. Vérifie et installe les dépendances système (apt)
#   2. Crée le virtual Python (.venv)
#   3. Installe les dépendances Python
#   4. Vérifie que tous les modules sont importables
#   5. Télécharge le modèle Vosk FR si absent
#
# Utilisation :
#   ./scripts/install.sh
#
# Prérequis :
#   - Python 3.10+ et pip
#   - Connexion internet (pour apt + modèle Vosk)
#   - Droits sudo (pour apt install)
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== hal-voice — Installation ==="

# ── 1. Dépendances système ───────────────────────────────────────────
# Vérifie les packages système nécessaires :
#   - libportaudio2 : backend audio pour sounddevice
#   - espeak-ng     : moteur TTS pour pyttsx3 (Linux)
#   - pulseaudio-utils : parecord/paplay pour WSL2
echo ""
echo "[1/4] Vérification des dépendances système..."

MISSING=()

if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
    MISSING+=("libportaudio2")
fi

if ! command -v espeak-ng &>/dev/null && ! command -v espeak &>/dev/null; then
    MISSING+=("espeak-ng")
fi

# Sous WSL2, PulseAudio est requis pour le micro
if grep -qi microsoft /proc/version 2>/dev/null; then
    if ! command -v parecord &>/dev/null; then
        MISSING+=("pulseaudio-utils")
    fi
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "  Installation de : ${MISSING[*]}"
    sudo apt install -y "${MISSING[@]}"
else
    echo "  OK — toutes les dépendances système sont présentes."
fi

# ── 2. Python venv ───────────────────────────────────────────────────
# Crée un environnement virtuel Python pour isoler les dépendances.
echo ""
echo "[2/4] Création du virtual environment..."

VENV_DIR="$PROJECT_DIR/.venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "  OK — venv existant détecté ($VENV_DIR)."
else
    python3 -m venv "$VENV_DIR"
    echo "  OK — venv créé."
fi
source "$VENV_DIR/bin/activate"

# ── 3. Dépendances Python ────────────────────────────────────────────
# Installe les packages depuis requirements.txt + le package en editable.
echo ""
echo "[3/4] Installation des dépendances Python..."
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q
pip install -e "$PROJECT_DIR" -q
echo "  OK — packages installés."

# ── 4. Vérification ──────────────────────────────────────────────────
# Vérifie que chaque module critique est importable.
echo ""
echo "[4/4] Vérification..."

python -c "import sounddevice" 2>/dev/null || { echo "  ✗ sounddevice — PortAudio manquant"; exit 1; }
python -c "import vosk"         2>/dev/null || { echo "  ✗ vosk"; exit 1; }
python -c "import pyttsx3"      2>/dev/null || { echo "  ✗ pyttsx3"; exit 1; }
python -c "import pynput"       2>/dev/null || { echo "  ✗ pynput"; exit 1; }
echo "  OK — tous les modules Python sont importables."

# ── Modèle Vosk ──────────────────────────────────────────────────────
# Télécharge le modèle de reconnaissance vocale français (~40 Mo).
MODEL_DIR="$PROJECT_DIR/models/vosk-model-small-fr-0.22"
if [ -d "$MODEL_DIR" ]; then
    echo "  OK — modèle Vosk FR présent."
else
    echo "  Téléchargement du modèle Vosk FR..."
    mkdir -p "$PROJECT_DIR/models"
    cd "$PROJECT_DIR/models"
    curl -sL https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip -o vosk-model.zip
    unzip -qo vosk-model.zip
    rm vosk-model.zip
    echo "  OK — modèle Vosk FR installé."
fi

echo ""
echo "=== Installation terminée ! ==="
echo "Lance hal-voice avec : ./scripts/run.sh"
