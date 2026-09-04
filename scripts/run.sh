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

    # Vérifie PulseAudio Windows (TCP 4713)
    HOST_IP=$(ip route show default 2>/dev/null | awk '{print $3}')
    if [ -n "$HOST_IP" ]; then
        if ! timeout 2 bash -c "echo >/dev/tcp/$HOST_IP/4713" 2>/dev/null; then
            echo "PulseAudio Windows non accessible sur $HOST_IP:4713"
            echo "Démarrage de PulseAudio Windows..."

            PA_DIR="$(cmd.exe /C "echo %LOCALAPPDATA%\pulseaudio\pulseaudio" 2>/dev/null | tr -d '\r')"
            PA_EXE="$PA_DIR/bin/pulseaudio.exe"
            PA_CONF="$PA_DIR/etc/halvoice.pa"

            # Convertit le chemin Windows → WSL
            PA_EXE_WSL=$(wslpath -u "$PA_EXE" 2>/dev/null || echo "")
            PA_CONF_WSL=$(wslpath -u "$PA_CONF" 2>/dev/null || echo "")

            if [ -n "$PA_EXE_WSL" ] && [ -f "$PA_EXE_WSL" ]; then
                # Nettoie les PID files stale
                powershell.exe -Command "Remove-Item '\$env:USERPROFILE\.config\pulse\*-runtime\pid' -Force -ErrorAction SilentlyContinue" 2>/dev/null
                # Lance via powershell.exe
                powershell.exe -Command "Start-Process -FilePath '$PA_EXE' -ArgumentList '-F','$PA_CONF' -WindowStyle Hidden" 2>/dev/null
                echo "En attente du démarrage..."
                sleep 3
                if timeout 2 bash -c "echo >/dev/tcp/$HOST_IP/4713" 2>/dev/null; then
                    echo "PulseAudio Windows démarré."
                else
                    echo "ERREUR: PulseAudio Windows n'a pas démarré."
                    echo "Lance-le manuellement :"
                    echo "  $PA_EXE -F $PA_CONF"
                    exit 1
                fi
            else
                echo "PulseAudio Windows introuvable : $PA_EXE"
                echo "Installe-le depuis : https://github.com/pgaskin/pulseaudio-win32"
                exit 1
            fi
        fi
    fi
fi

cd "$PROJECT_DIR/src"
exec python -m hal_voice "$@"
