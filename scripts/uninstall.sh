#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# uninstall.sh — Désinstallation de hal-voice (Linux / WSL2)
#
# Par défaut : supprime le venv et le modèle Vosk (safe).
# Avec --full : supprime aussi les dépendances système installées.
#
# Utilisation :
#   ./scripts/uninstall.sh           # safe — garde les paquets système
#   ./scripts/uninstall.sh --full    # tout supprimer, y compris apt
#   ./scripts/uninstall.sh --check   # affiche ce qui serait supprimé
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FULL_REMOVE=false
CHECK_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --full)   FULL_REMOVE=true ;;
        --check)  CHECK_ONLY=true ;;
        --help|-h)
            echo "Utilisation : ./scripts/uninstall.sh [--full] [--check]"
            echo "  --full   Supprime aussi les dépendances système (apt)"
            echo "  --check  Affiche ce qui serait supprimé sans rien faire"
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
info() { local msg="$1"; echo -e "  → $msg"; }

echo "══════════════════════════════════════"
echo "  hal-voice — Désinstallation"
echo "══════════════════════════════════════"

# ══════════════════════════════════════════════════════════════════════
# 1. Virtual environment
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "── 1. Virtual environment ──"

VENV_DIR="$PROJECT_DIR/.venv"
if [[ -d "$VENV_DIR" ]]; then
    if $CHECK_ONLY; then
        info "Supprimer : $VENV_DIR"
    else
        rm -rf "$VENV_DIR"
        ok "venv supprimé"
    fi
else
    ok "venv absent (rien à faire)"
fi

# ══════════════════════════════════════════════════════════════════════
# 2. Modèle Vosk
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "── 2. Modèle Vosk FR ──"

MODEL_DIR="$PROJECT_DIR/models/vosk-model-small-fr-0.22"
if [[ -d "$MODEL_DIR" ]]; then
    if $CHECK_ONLY; then
        info "Supprimer : $MODEL_DIR (~40 Mo)"
    else
        rm -rf "$MODEL_DIR"
        ok "modèle Vosk supprimé"
    fi
else
    ok "modèle absent (rien à faire)"
fi

# Nettoie le dossier models s'il est vide
if [[ -d "$PROJECT_DIR/models" ]]; then
    [[ -z "$(ls -A "$PROJECT_DIR/models" 2>/dev/null)" ]] && rmdir "$PROJECT_DIR/models"
fi

# ══════════════════════════════════════════════════════════════════════
# 3. Fichiers temporaires
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "── 3. Fichiers temporaires ──"

CLEANED=0
for pattern in "__pycache__" "*.pyc" "*.pyo" ".pytest_cache" "*.egg-info"; do
    while IFS= read -r -d '' f; do
        if $CHECK_ONLY; then
            info "Supprimer : $f"
        else
            rm -rf "$f"
        fi
        CLEANED=$((CLEANED + 1))
    done < <(find "$PROJECT_DIR" -name "$pattern" -not -path "*/.git/*" -print0 2>/dev/null)
done

if [[ $CLEANED -gt 0 ]]; then
    ok "$CLEANED éléments nettoyés"
else
    ok "déjà propre"
fi

# ══════════════════════════════════════════════════════════════════════
# 4. Dépendances système (--full uniquement)
# ══════════════════════════════════════════════════════════════════════
echo ""
echo "── 4. Dépendances système ──"

if ! $FULL_REMOVE; then
    info "Utilise --full pour supprimer les paquets système"
    info "Conservés : espeak-ng, curl, unzip, pulseaudio-utils"
else
    PACKAGES_TO_REMOVE=()

    # Vérifie chaque paquet avant de le supprimer
    for pkg in espeak-ng curl unzip pulseaudio-utils; do
        if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            PACKAGES_TO_REMOVE+=("$pkg")
            info "à supprimer : $pkg"
        fi
    done

    if [[ ${#PACKAGES_TO_REMOVE[@]} -gt 0 ]]; then
        if $CHECK_ONLY; then
            info "sudo apt remove -y ${PACKAGES_TO_REMOVE[*]}"
        else
            warn "Suppression de ${PACKAGES_TO_REMOVE[*]}..."
            sudo apt remove -y "${PACKAGES_TO_REMOVE[@]}"
            ok "paquets supprimés"
        fi
    else
        ok "aucun paquet à supprimer"
    fi

    # PulseAudio Windows (WSL2)
    if grep -qi microsoft /proc/version 2>/dev/null; then
        PA_DIR="${LOCALAPPDATA:-/mnt/c/Users/*/AppData/Local}/pulseaudio/pulseaudio"
        PA_EXPANDED=$(eval echo "$PA_DIR" 2>/dev/null | head -1)
        if [[ -d "$PA_EXPANDED" ]]; then
            if $CHECK_ONLY; then
                info "PulseAudio Windows : $PA_EXPANDED (suppression manuelle requise)"
            else
                warn "PulseAudio Windows détecté : $PA_EXPANDED"
                echo "    → Supprime-le manuellement depuis Windows si souhaité"
            fi
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════
# Résumé
# ══════════════════════════════════════════════════════════════════════
echo ""
if $CHECK_ONLY; then
    echo -e "${YELLOW}═══ Vérification terminée (rien n'a été supprimé) ═══${NC}"
elif $FULL_REMOVE; then
    echo -e "${GREEN}═══ Désinstallation complète terminée ═══${NC}"
    echo "Relance l'installation : ./scripts/install.sh"
else
    echo -e "${GREEN}═══ Désinstallation terminée (partielle) ═══${NC}"
    echo "Paquets système conservés. Pour tout supprimer : --full"
fi
