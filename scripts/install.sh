#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# install.sh — Installeur hal-voice pour Linux / WSL2
#
# Ce script :
#   1. Vérifie Python 3.10+
#   2. Détecte et installe les dépendances système (apt)
#   3. Crée le virtual Python (.venv)
#   4. Installe les dépendances Python
#   5. Vérifie que tous les modules sont importables
#   6. Télécharge le modèle Vosk FR si absent
#
# Utilisation :
#   ./scripts/install.sh           # installation complète
#   ./scripts/install.sh --check   # vérification sans installer
#
# Prérequis :
#   - Python 3.10+ et pip
#   - Connexion internet (pour apt + modèle Vosk)
#   - Droits sudo (pour apt install)
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CHECK_ONLY=false
ERRORS=0

[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

# ── Couleurs ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERRORS=$((ERRORS + 1)); }
info() { echo -e "  ${CYAN}→${NC} $1"; }

echo "=== hal-voice — Installation ==="
echo ""

# ══════════════════════════════════════════════════════════════════════
# 1. Python
# ══════════════════════════════════════════════════════════════════════
echo "[1/6] Python..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    fail "Python 3.10+ requis. Installe-le avec : sudo apt install python3 python3-venv"
elif $CHECK_ONLY; then
    ok "Python $($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+\.\d+')"
fi

# Vérifie pip
if [ -n "$PYTHON_CMD" ]; then
    if "$PYTHON_CMD" -m pip --version &>/dev/null; then
        ok "pip disponible"
    else
        fail "pip manquant. Installe-le avec : sudo apt install python3-pip"
    fi
fi

# ══════════════════════════════════════════════════════════════════════
# 2. Dépendances système
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "[2/6] Dépendances système..."

# Détecte le gestionnaire de paquets
PKG_MGR=""
if command -v apt &>/dev/null; then
    PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
elif command -v pacman &>/dev/null; then
    PKG_MGR="pacman"
fi

if [ -z "$PKG_MGR" ]; then
    warn "Gestionnaire de paquets non reconnu — vérification manuelle requise"
fi

# Sous WSL2 ?
IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    ok "WSL2 détecté"
fi

# --- libportaudio2 (audio I/O) ---
if ldconfig -p 2>/dev/null | grep -q libportaudio; then
    ok "libportaudio2"
elif [ -n "$PKG_MGR" ] && ! $CHECK_ONLY; then
    warn "libportaudio2 manquant — installation..."
    case "$PKG_MGR" in
        apt)    sudo apt install -y libportaudio2 ;;
        dnf)    sudo dnf install -y portaudio-devel ;;
        pacman) sudo pacman -S --noconfirm portaudio ;;
    esac
    ok "libportaudio2 installé"
else
    fail "libportaudio2 manquant"
fi

# --- espeak-ng (TTS Linux) ---
if command -v espeak-ng &>/dev/null; then
    ok "espeak-ng"
elif command -v espeak &>/dev/null; then
    warn "espeak trouvé (préfère espeak-ng pour de meilleurs résultats FR)"
elif [ -n "$PKG_MGR" ] && ! $CHECK_ONLY; then
    warn "espeak-ng manquant — installation..."
    case "$PKG_MGR" in
        apt)    sudo apt install -y espeak-ng ;;
        dnf)    sudo dnf install -y espeak-ng ;;
        pacman) sudo pacman -S --noconfirm espeak-ng ;;
    esac
    ok "espeak-ng installé"
else
    fail "espeak-ng manquant"
fi

# --- pulseaudio-utils (WSL2 uniquement) ---
if $IS_WSL; then
    if command -v parecord &>/dev/null; then
        ok "pulseaudio-utils"
    elif [ -n "$PKG_MGR" ] && ! $CHECK_ONLY; then
        warn "pulseaudio-utils manquant — installation..."
        case "$PKG_MGR" in
            apt)    sudo apt install -y pulseaudio-utils ;;
            dnf)    sudo dnf install -y pulseaudio-utils ;;
            pacman) sudo pacman -S --noconfirm libpulse ;;
        esac
        ok "pulseaudio-utils installé"
    else
        fail "pulseaudio-utils manquant (requis pour WSL2)"
    fi

    # --- PulseAudio Windows (host) ---
    PA_DIR="${LOCALAPPDATA:-/mnt/c/Users/*/AppData/Local}/pulseaudio/pulseaudio"
    PA_DIR_EXPANDED=$(eval echo "$PA_DIR" 2>/dev/null | head -1)
    if [ -f "$PA_DIR_EXPANDED/bin/pulseaudio.exe" ]; then
        ok "PulseAudio Windows trouvé"
    else
        warn "PulseAudio Windows non trouvé — micro indisponible sous WSL2"
        info "Installe-le depuis : https://github.com/pgaskin/pulseaudio-win32"
    fi
fi

# --- curl + unzip (téléchargement modèle Vosk) ---
if command -v curl &>/dev/null; then
    ok "curl"
else
    fail "curl manquant (requis pour télécharger le modèle Vosk)"
fi

if command -v unzip &>/dev/null; then
    ok "unzip"
else
    fail "unzip manquant (requis pour extraire le modèle Vosk)"
fi

# ══════════════════════════════════════════════════════════════════════
# 3. Python venv
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "[3/6] Virtual environment..."

VENV_DIR="$PROJECT_DIR/.venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
    ok "venv existant ($VENV_DIR)"
elif $CHECK_ONLY; then
    fail "venv absent"
else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    ok "venv créé"
fi

if [ -f "$VENV_DIR/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
fi

# ══════════════════════════════════════════════════════════════════════
# 4. Dépendances Python
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "[4/6] Dépendances Python..."

if $CHECK_ONLY; then
    # En mode vérification, on teste juste l'import
    python -c "import sounddevice" 2>/dev/null && ok "sounddevice" || fail "sounddevice manquant"
    python -c "import vosk"         2>/dev/null && ok "vosk"         || fail "vosk manquant"
    python -c "import pynput"       2>/dev/null && ok "pynput"       || fail "pynput manquant"
    if [[ "$(uname -s)" != *"MINGW"* ]]; then
        python -c "import pyttsx3"  2>/dev/null && ok "pyttsx3"      || fail "pyttsx3 manquant"
    fi
else
    pip install --upgrade pip -q
    pip install -r "$PROJECT_DIR/requirements.txt" -q
    pip install -e "$PROJECT_DIR" -q
    ok "packages installés"
fi

# ══════════════════════════════════════════════════════════════════════
# 5. Vérification des imports
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "[5/6] Vérification des modules Python..."

MODULES=(
    "sounddevice:PortAudio (sounddevice)"
    "soundfile:soundfile"
    "vosk:Vosk (STT)"
    "pynput:pynput (hotkeys)"
)

# Modules spécifiques à la plateforme
if [[ "$(uname -s)" == *"MINGW"* ]] || [[ "$(uname -s)" == *"MSYS"* ]]; then
    MODULES+=("win32com:pywin32 (TTS SAPI)")
else
    MODULES+=("pyttsx3:pyttsx3 (TTS)")
fi

for entry in "${MODULES[@]}"; do
    mod="${entry%%:*}"
    label="${entry#*:}"
    python -c "import $mod" 2>/dev/null && ok "$label" || fail "$label manquant"
done

# ══════════════════════════════════════════════════════════════════════
# 6. Modèle Vosk
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "[6/6] Modèle Vosk FR..."

MODEL_DIR="$PROJECT_DIR/models/vosk-model-small-fr-0.22"
if [ -d "$MODEL_DIR" ]; then
    ok "modèle Vosk FR présent"
elif $CHECK_ONLY; then
    fail "modèle Vosk FR absent"
else
    info "Téléchargement du modèle Vosk FR (~40 Mo)..."
    mkdir -p "$PROJECT_DIR/models"
    cd "$PROJECT_DIR/models"
    if curl -sL https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip -o vosk-model.zip; then
        unzip -qo vosk-model.zip
        rm vosk-model.zip
        ok "modèle Vosk FR installé"
    else
        fail "Échec du téléchargement du modèle Vosk"
        rm -f vosk-model.zip
    fi
    cd "$PROJECT_DIR"
fi

# ══════════════════════════════════════════════════════════════════════
# Résumé
# ══════════════════════════════════════════════════════════════════════
echo ""
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}=== Installation terminée avec $ERRORS erreur(s) ===${NC}"
    echo "Corrige les erreurs ci-dessus puis relance : ./scripts/install.sh"
    exit 1
else
    echo -e "${GREEN}=== Installation terminée ! ===${NC}"
    echo "Lance hal-voice avec : ./scripts/run.sh"
fi
