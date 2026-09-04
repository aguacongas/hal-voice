#!/usr/bin/env bash
# Usage: test-mic-device.sh <pulse_server_ip> <device_index>
# Records 2s from the given PulseAudio source, prints max amplitude.

set -euo pipefail

HOST_IP="${1:?Usage: $0 <host_ip> <device_index>}"
DEVICE_INDEX="${2:-0}"

export PULSE_SERVER="tcp:$HOST_IP"

# Map PulseAudio source name from device index
# device 0 -> wavein, device 2 -> wavein.2, etc.
if [ "$DEVICE_INDEX" -eq 0 ]; then
    SOURCE="wavein"
else
    SOURCE="wavein.${DEVICE_INDEX}"
fi

TMPFILE="/tmp/halvoice_test.raw"

# Record 2 seconds
timeout 3 parecord --device="$SOURCE" --format=s16le --rate=16000 --channels=1 --raw "$TMPFILE" 2>/dev/null || true

if [ ! -f "$TMPFILE" ] || [ ! -s "$TMPFILE" ]; then
    echo "0"
    exit 0
fi

# Check amplitude with python
python3 -c "
import numpy as np
d = np.fromfile('$TMPFILE', dtype=np.int16)
print(d.max())
" 2>/dev/null || echo "0"
