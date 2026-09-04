#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# run.sh — Lanceur principal de hal-voice pour Linux/WSL2.
#
# Ce script :
#   1. Crée le virtual Python si absent et installe les dépendances
#   2. Vérifie les dépendances système (libportaudio, espeak-ng, parecord)
#   3. Sous WSL2 : démarre PulseAudio Windows si nécessaire
#   4. Lance ``python -m hal_voice`` avec les arguments transmis
#
# Utilisation :
#   ./scripts/run.sh              # mode normal (boucle vocale)
#   ./scripts/run.sh --diagnose   # diagnostic PulseAudio
#   ./scripts/run.sh --test       # test record/replay 3s
#   ./scripts/run.sh --silent     # boucle sans synthèse vocale (TTS muet)
#
# Notes WSL2 :
#   - PulseAudio Windows doit tourner sur l'hôte pour capturer le micro
#   - Le serveur est accessible via TCP sur le port 4713
#   - Si PulseAudio ne tourne pas, ce script le démarre automatiquement
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Virtual Python ────────────────────────────────────────────────────
# Crée le venv et installe les dépendances si c'est la première fois.
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
# Vérifie que les libs système essentielles sont installées.
# libportaudio2 : backend audio pour sounddevice (Windows natif)
# espeak-ng     : moteur TTS pour pyttsx3 (fallback Linux)
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
# Sous WSL2, on a besoin de pulseaudio-utils pour parecord/paplay.
# On vérifie aussi que PulseAudio Windows est accessible sur TCP 4713.
if grep -qi microsoft /proc/version 2>/dev/null; then
    if ! command -v parecord &>/dev/null; then
        echo "pulseaudio-utils manquant (parecord)."
        echo "Installe-le avec : sudo apt install pulseaudio-utils"
        exit 1
    fi

    # Récupère l'IP Windows depuis la route par défaut WSL
    HOST_IP=$(ip route show default 2>/dev/null | awk '{print $3}')
    if [ -n "$HOST_IP" ]; then
        # Teste si le port 4713 est accessible (timeout 2s)
        if ! timeout 2 bash -c "echo >/dev/tcp/$HOST_IP/4713" 2>/dev/null; then
            echo "PulseAudio Windows non accessible sur $HOST_IP:4713"
            echo "Démarrage de PulseAudio Windows..."

            # Récupère le chemin d'installation de PulseAudio via cmd.exe
            PA_DIR="$(cmd.exe /C "echo %LOCALAPPDATA%\pulseaudio\pulseaudio" 2>/dev/null | tr -d '\r')"
            PA_EXE="$PA_DIR/bin/pulseaudio.exe"
            PA_CONF="$PA_DIR/etc/halvoice.pa"

            # Convertit le chemin Windows → WSL (ex: C:\Users\... → /mnt/c/Users/...)
            PA_EXE_WSL=$(wslpath -u "$PA_EXE" 2>/dev/null || echo "")
            PA_CONF_WSL=$(wslpath -u "$PA_CONF" 2>/dev/null || echo "")

            if [ -n "$PA_EXE_WSL" ] && [ -f "$PA_EXE_WSL" ]; then
                # Supprime les PID files stale (restes d'un précédent arrêt brutal)
                powershell.exe -Command "Remove-Item '\$env:USERPROFILE\.config\pulse\*-runtime\pid' -Force -ErrorAction SilentlyContinue" 2>/dev/null
                # Lance PulseAudio en arrière-plan via PowerShell Start-Process
                powershell.exe -Command "Start-Process -FilePath '$PA_EXE' -ArgumentList '-F','$PA_CONF' -WindowStyle Hidden" 2>/dev/null
                echo "En attente du démarrage..."
                sleep 3
                # Vérifie que le port 4713 est maintenant accessible
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

# ── Lancement ─────────────────────────────────────────────────────────
# On exécute ``python -m hal_voice`` depuis le dossier src/ pour que
# le package soit trouvé correctement.
cd "$PROJECT_DIR/src"
exec python -m hal_voice "$@"
