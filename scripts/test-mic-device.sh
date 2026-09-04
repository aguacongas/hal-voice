#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# test-mic-device.sh — Teste si un device PulseAudio capture du son.
#
# Ce script est appelé par detect-mic.ps1 depuis PowerShell pour tester
# chaque device WaveIn. Il enregistre 2 secondes via parecord et
# retourne l'amplitude maximale (int).
#
# Usage :
#   ./test-mic-device.sh <host_ip> <device_index>
#
# Arguments :
#   host_ip      — IP de la machine Windows (ex: 172.17.192.1)
#   device_index — Index WaveIn du device à tester (ex: 0, 1, 2)
#
# Sortie :
#   Un nombre entier = amplitude maximale (0 = silence, >100 = son capté)
#
# Fonctionnement :
#   1. Connecte parecord au serveur PulseAudio Windows via TCP
#   2. Map l'index WaveIn vers le nom source PulseAudio
#      (index 0 → wavein, index 2 → wavein.2, etc.)
#   3. Enregistre 2 secondes en PCM brut s16le, mono, 16 kHz
#   4. Utilise numpy pour calculer l'amplitude max
#   5. Retourne le résultat sur stdout
#
# Pièges gérés :
#   - timeout 3 pour éviter que parecord tourne indéfiniment
#   - || true pour ignorer le code de sortie de timeout
#   - Fichier temporaire /tmp pour éviter les conflits
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

HOST_IP="${1:?Usage: $0 <host_ip> <device_index>}"
DEVICE_INDEX="${2:-0}"

# Connecte au serveur PulseAudio Windows
export PULSE_SERVER="tcp:$HOST_IP"

# Map l'index WaveIn vers le nom source PulseAudio
# module-waveout crée les sources wavein, wavein.2, wavein.3, etc.
if [ "$DEVICE_INDEX" -eq 0 ]; then
    SOURCE="wavein"
else
    SOURCE="wavein.${DEVICE_INDEX}"
fi

TMPFILE="/tmp/halvoice_test.raw"

# Enregistre 2 secondes en PCM brut s16le
# --raw : pas de header WAV, juste les données brutes
# timeout 3 : parecord n'a pas d'option --duration, on le force à s'arrêter
timeout 3 parecord --device="$SOURCE" --format=s16le --rate=16000 --channels=1 --raw "$TMPFILE" 2>/dev/null || true

# Vérifie que le fichier a été créé et contient des données
if [ ! -f "$TMPFILE" ] || [ ! -s "$TMPFILE" ]; then
    echo "0"
    exit 0
fi

# Calcule l'amplitude maximale avec numpy
# d.max() : plus grand échantillon (0-32767 pour int16)
# Un silence parfait donne 0, un micro actif donne >100
python3 -c "
import numpy as np
d = np.fromfile('$TMPFILE', dtype=np.int16)
print(d.max())
" 2>/dev/null || echo "0"
