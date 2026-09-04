#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Venv ──────────────────────────────────────────────────────────────
VENV_DIR="$PROJECT_DIR/.venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Création du venv..."
    python3 -m venv "$VENV_DIR"
    echo "Installation des dépendances..."
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
    "$VENV_DIR/bin/pip" install -e "$PROJECT_DIR"
fi
source "$VENV_DIR/bin/activate"

# ── Dépendances système ──────────────────────────────────────────────
MISSING=()

if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
    MISSING+=("libportaudio2")
fi

if ! command -v espeak-ng &>/dev/null && ! command -v espeak &>/dev/null; then
    MISSING+=("espeak-ng")
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Dépendances système manquantes : ${MISSING[*]}"
    echo "Installe-les avec :"
    echo "  sudo apt install ${MISSING[*]}"
    exit 1
fi

# ── Vérification audio (WSL2 / WSLg) ─────────────────────────────────
if grep -qi microsoft /proc/version 2>/dev/null; then
    if ! command -v parecord &>/dev/null; then
        echo "pulseaudio-utils manquant (parecord)."
        echo "Installe-le avec : sudo apt install pulseaudio-utils"
        exit 1
    fi
fi

cd "$PROJECT_DIR/src"
exec python -m hal_voice "$@"
