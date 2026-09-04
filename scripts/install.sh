#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# install.sh — Installation automatique de hal-voice (Linux / WSL2)
#
# Une seule commande installe TOUT :
#   ./scripts/install.sh
#
# Ce script :
#   1. Installe Python 3.10+ si absent
#   2. Installe les dépendances système (espeak-ng, curl, unzip, etc.)
#   3. Installe uv (gestionnaire de dép) et synchronise .venv (uv sync)
#   4. Vérifie les imports
#   5. Télécharge le modèle Vosk FR (~40 Mo)
#
# Options :
#   --check    Vérifie sans rien installer (dry-run)
#   --skip-apt Saute les installations apt (utile si pas sudo)
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CHECK_ONLY=false
SKIP_APT=false

for arg in "$@"; do
    case "$arg" in
        --check)    CHECK_ONLY=true ;;
        --skip-apt) SKIP_APT=true ;;
        --help|-h)
            echo "Utilisation : ./scripts/install.sh [--check] [--skip-apt]"
            echo "  --check    Vérifie sans rien installer"
            echo "  --skip-apt Saute les installations système"
            exit 0
            ;;
        *)
            echo "Option inconnue : $arg (ignorée)" >&2
            ;;
    esac
done

# ── Couleurs ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
ok()   { local msg="$1"; echo -e "  ${GREEN}✓${NC} $msg"; }
warn() { local msg="$1"; echo -e "  ${YELLOW}!${NC} $msg"; }
fail() { local msg="$1"; echo -e "  ${RED}✗${NC} $msg"; }
step() { local msg="$1"; echo -e "\n${GREEN}── $msg ──${NC}"; }

echo "══════════════════════════════════════"
echo "  hal-voice — Installation auto"
echo "══════════════════════════════════════"

# ══════════════════════════════════════════════════════════════════════
# 1. Python 3.10+
# ══════════════════════════════════════════════════════════════════════
step "1/6 — Python"

find_python() {
    local cmd ver major minor
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 10 ]]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_CMD=$(find_python || true)

if [[ -z "$PYTHON_CMD" ]]; then
    fail "Python 3.10+ introuvable"
    if $CHECK_ONLY || $SKIP_APT; then
        echo "  Installe-le manuellement : sudo apt install python3 python3-venv python3-pip"
        exit 1
    fi
    echo "  Installation de Python 3..."
    sudo apt update -qq
    sudo apt install -y python3 python3-venv python3-pip
    PYTHON_CMD=$(find_python || true)
    if [[ -z "$PYTHON_CMD" ]]; then
        fail "Échec installation Python"
        exit 1
    fi
fi
ok "Python $($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+\.\d+')"

# pip
if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
    warn "pip manquant — installation..."
    if ! $CHECK_ONLY && ! $SKIP_APT; then
        sudo apt install -y python3-pip
    fi
fi
"$PYTHON_CMD" -m pip --version &>/dev/null && ok "pip" || fail "pip manquant"

# ══════════════════════════════════════════════════════════════════════
# 2. Dépendances système
# ══════════════════════════════════════════════════════════════════════
step "2/6 — Paquets système"

IS_WSL=false
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=true

install_pkg() {
    local pkg="$1"
    local check_cmd="${2:-$pkg}"

    if command -v "$check_cmd" &>/dev/null; then
        ok "$pkg"
        return 0
    fi

    if $CHECK_ONLY || $SKIP_APT; then
        fail "$pkg manquant"
        return 1
    fi

    warn "$pkg manquant — installation..."
    sudo apt install -y "$pkg" 2>/dev/null && ok "$pkg installé" || fail "échec $pkg"
}

# Toujours installés
install_pkg espeak-ng espeak-ng
install_pkg curl curl
install_pkg unzip unzip

# WSL2 uniquement
if $IS_WSL; then
    install_pkg pulseaudio-utils parecord

    # PulseAudio Windows
    PA_EXE="${LOCALAPPDATA:-/mnt/c/Users/*/AppData/Local}/pulseaudio/pulseaudio/bin/pulseaudio.exe"
    PA_EXPANDED=$(eval echo "$PA_EXE" 2>/dev/null | head -1)
    if [[ -f "$PA_EXPANDED" ]]; then
        ok "PulseAudio Windows"
    else
        warn "PulseAudio Windows non trouvé — micro WSL2 indisponible"
        echo "    → https://github.com/pgaskin/pulseaudio-win32"
    fi
fi

# ══════════════════════════════════════════════════════════════════════
# 3. Virtual environment (uv)
# ══════════════════════════════════════════════════════════════════════
# Le projet utilise https://astral.sh/uv (gestionnaire moderne) : `uv sync`
# crée/synchronise .venv depuis pyproject.toml + uv.lock (déclaratif), puis
# installe le paquet en mode editable + les extras dev.
step "3/6 — Virtual environment (uv)"

VENV_DIR="$PROJECT_DIR/.venv"

if ! command -v uv &>/dev/null; then
    if $CHECK_ONLY || $SKIP_APT; then
        fail "uv manquant — installe-le : curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    warn "uv manquant — installation..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

if $CHECK_ONLY; then
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        ok "venv existant"
    else
        fail "venv absent"
    fi
else
    uv sync --extra dev
    ok "venv synchronisé (uv sync)"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ══════════════════════════════════════════════════════════════════════
# 4. Dépendances Python
# ══════════════════════════════════════════════════════════════════════
step "4/6 — Packages Python"

if $CHECK_ONLY; then
    for mod in soundfile vosk pynput pyttsx3; do
        python -c "import $mod" 2>/dev/null && ok "$mod" || fail "$mod manquant"
    done
else
    ok "packages installés (uv sync)"
fi

# ══════════════════════════════════════════════════════════════════════
# 5. Vérification des imports
# ══════════════════════════════════════════════════════════════════════
step "5/6 — Vérification"

MODULES="soundfile:soundfile
vosk:Vosk STT
pynput:hotkeys
pyttsx3:TTS"

ALL_OK=true
while IFS= read -r line; do
    mod="${line%%:*}"
    label="${line#*:}"
    python -c "import $mod" 2>/dev/null && ok "$label" || { fail "$label"; ALL_OK=false; }
done <<< "$MODULES"

# ══════════════════════════════════════════════════════════════════════
# 6. Modèle Vosk
# ══════════════════════════════════════════════════════════════════════
step "6/6 — Modèle Vosk FR"

MODEL_DIR="$PROJECT_DIR/models/vosk-model-small-fr-0.22"
if [[ -d "$MODEL_DIR" ]]; then
    ok "modèle présent"
elif $CHECK_ONLY; then
    fail "modèle absent"
else
    echo "  Téléchargement (~40 Mo)..."
    mkdir -p "$PROJECT_DIR/models"
    (
        cd "$PROJECT_DIR/models"
        curl -sL --fail --proto '=https' --tlsv1.2 \
            https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip \
            -o vosk-model.zip \
            && unzip -qo vosk-model.zip \
            && rm vosk-model.zip \
            && echo "OK"
    ) && ok "modèle installé" || fail "échec téléchargement"
fi

# ══════════════════════════════════════════════════════════════════════
# Résumé
# ══════════════════════════════════════════════════════════════════════
echo ""
if $ALL_OK; then
    echo -e "${GREEN}═══ Installation terminée ! ═══${NC}"
    echo "Lance : ./scripts/run.sh"
else
    echo -e "${YELLOW}═══ Installation terminée avec avertissements ═══${NC}"
    echo "Certains modules manquent — lance --check pour les lister"
fi
