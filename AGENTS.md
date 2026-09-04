# AGENTS.md

Instruction file for OpenCode sessions working in `hal-voice`.

## Project status

Python 3.10+ app: 100% local voice assistant — STT (Vosk, French offline) + TTS (pyttsx3/eSpeak) + audio I/O. **WSL2/Linux only** — no native Windows app support (SAPI/sounddevice removed). **v0.8.0** — boucle vocale interactive fonctionnelle.

- Layout: `src/hal_voice/` (Clean Architecture: `domain/`, `use_cases/`, `adapters/`), `tests/`, `scripts/`, `models/` (Vosk model, gitignored).
- Single package, real entrypoint `hal_voice.__main__:main` (also `python -m hal_voice`).

## Commands

- Main loop: `./scripts/run.sh` (WSL2/Linux) or `python -m hal_voice`. `run.sh` uses **uv** (`uv sync --extra dev` from `uv.lock`) to create/use `.venv`.
- **Diagnose PulseAudio under WSL**: `python -m hal_voice --diagnose` (or `./scripts/run.sh --diagnose`) → lists sources, chosen device, and does a 3 s capture reporting `max_amplitude`. **Always run this first when investigating mic issues.**
- Quick audio smoke test (record 3 s + replay): `python -m hal_voice.audio_io` (runs `quick_test()`).
- Silent mode (test STT without speaking): `./scripts/run.sh --silent`.
- Tests: `pytest` (from repo root). Hardware-dependent tests are marked `requires_hardware` (see `pyproject.toml` `[tool.pytest.ini_options]`). Most tests are mocked — don't assume a real mic.
- Lint: `ruff` (`line-length = 100`). Not installed in the default env; run via dev extra if needed.

## Config

`src/hal_voice/domain/config.py` (chargé via `adapters/config_loader.py`) — all tunables via env vars, no hardcoding in modules: `HAL_VOICE_MODEL_PATH`, `HAL_VOICE_SAMPLE_RATE` (default 16000), `HAL_VOICE_CHANNELS` (1), `HAL_VOICE_DTYPE` (int16), `HAL_VOICE_WAKE_WORD`.

## Audio capture (audio_io.py) — critical WSL2 knowledge

`AudioIO` uses the PulseAudio CLI (`parecord`/`paplay`) only (sounddevice/PortAudio removed — no native Windows). WSL2 detection = `"microsoft" in /proc/version`.

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

Resulting audio is mono int16 at the configured rate, fed to Vosk (`stt_vosk.py`). If no mic data, code returns a zeroed array (`_record_pulse` guards this).

## TTS

Adapter `adapters/tts.py`: pyttsx3 (needs `espeak-ng`) — SAPI5/win32com backend removed. Log line `Voix TTS selectionnee : ...` appears at startup.

**Voice selection** (`_select_voice`): prefers `FRENCH (France)` — `_is_france()` matches SAPI hex `40C` (0x040C=1036) or eSpeak BCP 47 `roa/fr`; then any FR voice (`_is_french()` matches `fr`, `fra`, `roa/fr-be`, …); then fallback. Watch out: `_lang_id_to_int` only handles hex — BCP tags never parse, that's why `_is_french`/`_is_france` handle the eSpeak string format directly.

**eSpeak-ng under WSL2 (critical)**: pyttsx3's espeak driver renders speech to a temp WAV then plays it via `os.system("aplay <wav> -q")`. `aplay` uses **ALSA** which has no sound card under WSL2 → "cannot find card '0'" errors and **NO AUDIBLE OUTPUT**. Fix already in `_configure_pulse_for_espeak()`:
1. Forces `PULSE_SERVER=tcp:<gateway>` (Windows PulseAudio) instead of WSLg — checked via `pactl info`.
2. `_write_asoundrc()` writes `~/.asoundrc` redirecting `pcm.!default`/`ctl.!default` → `type pulse` (needs `libasound2-plugins` installed, which `install.sh` ensures). This makes `aplay` route through PulseAudio. Idempotent — only writes if missing.

Both fixes run BEFORE `pyttsx3.init()` in `TTS.__init__`. If TTS is silent under WSL2, check `~/.asoundrc` exists and `PULSE_SERVER` is the tcp gateway (not `unix:/mnt/wslg/...`).

## Session notes

- `docs/SESSION-RESUME-INSTRUCTIONS.md` — **read this first** to resume work. Contains runtime state, quick tests, and next steps.
- `docs/SESSION-NOTES-2026-09-03.md` — initial WSL2/PulseAudio setup, gotchas, outstanding items.
- `docs/SESSION-NOTES-2026-09-04.md` — auto-detection, duplicate module-waveout fix, comments, docs.
- `docs/SESSION-NOTES-2026-09-05.md` — Clean Architecture refactor, install/setup scripts, TTS audible fix.
- `docs/SESSION-NOTES-2026-09-06.md` — retrait du support natif Windows (TTS/audio/deps/scripts/docs).
- `docs/SESSION-NOTES-2026-09-07.md` — CI/SonarCloud verts, couverture 93%, merge de la PR #1 (wsl2-support → main, branche supprimée).

## Conventions

- French docstrings/comments and log messages throughout.
- `ruff` at 100 cols; keep lines ≤ 100.
- `import numpy as np`; audio buffers are `np.int16`.
- Do not commit `models/`, `*.wav`, `__pycache__`, `.venv/` (gitignored).
