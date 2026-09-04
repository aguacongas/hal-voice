# AGENTS.md

Instruction file for OpenCode sessions working in `hal-voice`.

## Project status

Python 3.10+ app: 100% local voice assistant — STT (Vosk, French offline) + TTS (SAPI5/pyttsx3) + audio I/O. **v0.5.0** — boucle vocale interactive fonctionnelle.

- Layout: `src/hal_voice/` (package, setuptools `src` layout), `tests/`, `scripts/` (install/run per-OS), `models/` (Vosk model, gitignored).
- Single package, real entrypoint `hal_voice.__main__:main` (also `python -m hal_voice`).

## Commands

- Main loop: `python -m hal_voice` (Windows) or `./scripts/run.sh` (Linux/WSL). Proxy in `scripts/run.bat`/`run.sh`, which create/use `.venv` and `pip install -e`.
- **Diagnose PulseAudio under WSL**: `python -m hal_voice --diagnose` (or `./scripts/run.sh --diagnose`) → lists sources, chosen device, and does a 3 s capture reporting `max_amplitude`. **Always run this first when investigating mic issues.**
- Quick audio smoke test (record 3 s + replay): `python -m hal_voice.audio_io` (runs `quick_test()`).
- Tests: `pytest` (from repo root). Hardware-dependent tests are marked `requires_hardware`; Windows-only ones `requires_windows` (see `pyproject.toml` `[tool.pytest.ini_options]`). Most tests are mocked — don't assume a real mic.
- Lint: `ruff` (`line-length = 100`). Not installed in the default env; run via dev extra if needed.

## Config

`src/hal_voice/config.py` — all tunables via env vars, no hardcoding in modules: `HAL_VOICE_MODEL_PATH`, `HAL_VOICE_SAMPLE_RATE` (default 16000), `HAL_VOICE_CHANNELS` (1), `HAL_VOICE_DTYPE` (int16), `HAL_VOICE_WAKE_WORD`.

## Audio capture (audio_io.py) — critical WSL2 knowledge

`AudioIO` auto-switches: `sounddevice` (PortAudio) normally, but under WSL2 uses PulseAudio CLI (`parecord`/`paplay`). WSL2 detection = `"microsoft" in /proc/version`.

**WSLg does NOT bridge the Windows microphone.** Only audio *output* works via WSLg. The input device seen there (`RDPSource`) returns only silence. To capture the mic under WSL2, the working setup is:
- **PulseAudio for Windows** (port 4713 TCP, `auth-anonymous=1`, `module-waveout record=1`) installed on the host, exposing the mic as a source (`wavein`).
- WSL `.bashrc` exports `PULSE_SERVER="tcp:$(ip route show default | awk '{print $3}')"` (dynamic host IP). Note `.bashrc` only loads in interactive shells; `wsl.exe -- bash -lc` (non-interactive) does NOT pick it up, which confuses probe scripts.

**`parecord` (Debian/Ubuntu build in WSL) gotchas** — a future agent WILL hit these:
- It has **no `--duration` option**; a bare `parecord` records forever → you must read a fixed number of bytes then `terminate()`/`kill()`.
- **`--file-format=wav` writing to `/dev/stdout` fails** with "Failed to open audio file" (returns 0 bytes) because stdout is a pipe. Writing to a **real temp file** (suffix `.raw` → forces raw s16le, no WAV header) works. `_record_pulse` already implements this.
- `module-waveout` (PulseAudio for Windows) needs an **explicit `input_device=<index>`**; it does NOT follow the Windows default mic automatically. The index order comes from the WaveIn API and differs per machine. `input_device` must be an index; passing `device=` or `input_device_name` mis-sets/errors on the pgaskin build (it prints `device and device_name are no longer supported`).
- A stale PulseAudio pid file (`%USERPROFILE%\.config\pulse\WSSIEN237-runtime\pid`) causes a spurious "Daemon already running" on restart — delete the runtime dir when restarting.

**Duplicate `module-waveout`**: `default.pa` may load `module-waveout` without `input_device`, creating a silent `wavein` source. Then `halvoice.pa` loads it again with the correct `input_device`, creating `wavein.2`. Comment out the line in `default.pa` to fix.

**Auto-detection**: `_pulse_find_input_device()` probes each source with a 1 s capture (`_test_source_amplitude()`) and picks the one with the highest amplitude. If only one source exists, it's used directly.

Resulting audio is mono int16 at the configured rate, fed to Vosk (`stt_vosk.py`). If no mic data, code returns a zeroed array (both `_record_sounddevice`/`_record_pulse` guard this).

## TTS

`tts_sapi.py`: Windows → SAPI5 via `win32com`; Linux/WSL → `pyttsx3` (needs `espeak-ng`). Log line `Voix TTS selectionnee : ...` appears at startup.

## Session notes

- `docs/SESSION-RESUME-INSTRUCTIONS.md` — **read this first** to resume work. Contains runtime state, quick tests, and next steps.
- `docs/SESSION-NOTES-2026-09-03.md` — initial WSL2/PulseAudio setup, gotchas, outstanding items.
- `docs/SESSION-NOTES-2026-09-04.md` — auto-detection, duplicate module-waveout fix, comments, docs.

## Conventions

- French docstrings/comments and log messages throughout.
- `ruff` at 100 cols; keep lines ≤ 100.
- `import numpy as np`; audio buffers are `np.int16`.
- Do not commit `models/`, `*.wav`, `__pycache__`, `.venv/` (gitignored).
