"""Entry point: `python -m hal_voice`."""

from __future__ import annotations

import sys


def main() -> int:
    print("hal-voice v0.1.0 — skeleton ready, no logic yet.")
    print("Modules planned: audio_io, stt_vosk, tts_sapi, wakeword, hotkey, commands.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
