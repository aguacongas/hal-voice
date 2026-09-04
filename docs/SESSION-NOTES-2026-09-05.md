# Session notes — 2026-09-05

## Objectif

Refonte en Clean Architecture, scripts d'installation/uninstallation complets, et surtout **rendre le TTS audible sous WSL2** (il était silencieux). Mise à jour des dépendances.

## Travail réalisé

### 1. Refonte Clean Architecture (commit `373c784` + `e6cc0bf`)

Structure `src/hal_voice/` réorganisée, **sans back-compat** (le produit est en dev, pas v1) :
- `domain/entities.py` → `Intent`
- `domain/protocols.py` → `ISTT`, `ITTS`, `IAudioCapture`, `IAudioPlayback`
- `domain/config.py` → `Config` (dataclass frozen) + constantes
- `use_cases/command_parser.py`, `use_cases/orchestrator.py` → logique métier, ne dépend que des protocoles
- `adapters/` → `config_loader.py`, `stt_vosk.py`, `tts.py`, `audio_io.py`, `hotkey.py` (implémentations concrètes)
- DI dans `__main__.py`

Les modules legacy (`commands.py`, `config.py`, `audio_io.py`, `stt_vosk.py`, `tts_sapi.py`, `hotkey.py`) ont été **supprimés** ; les tests importent les nouveaux chemins.

### 2. Scripts d'installation (commits `156f3c8` → `c56a13f`)

- `scripts/install.sh` : auto-installe Python 3.10+, deps système, multi-distro (apt/dnf/pacman), `--check` / `--skip-apt`.
- `scripts/uninstall.sh` : safe par défaut ; `--full` retire les paquets apt ; `--check` dry-run.
- `scripts/setup.bat` (Windows) : installe WSL2 + Ubuntu + PulseAudio pgaskin, configure `halvoice.pa`/`default.pa`, autostart, puis lance install.sh dans WSL.
- `scripts/teardown.bat` : safe ; `--full` retire WSL2 + Ubuntu ; `--check`.

### 3. Dépendances à jour (commit `90889db`)

sounddevice≥0.5.6, soundfile≥0.14.0, pyttsx3≥2.99, pynput≥1.8.2, pytest≥9.1.1, ruff≥0.16.6, pyyaml≥6.0.2. `keyboard` supprimé (remplacé par pynput). Classifier Python 3.13 ajouté.

### 4. Fix TTS : sélection voix FR (commits `142045b`, `d159304`)

- `_is_french()` traitait les IDs **BCP 47/eSpeak** (`roa/fr`, `roa/fr-be`) en plus des hex SAPI (`40C`). Avant, `_lang_id_to_int` faisait une comparaison hex qui ne matchait jamais les tags BCP → la **première voix trouvée était "Afrikaans" (gmw/en)**.
- `_is_france()` : détecte le **français de France** exclusivement (`0x040C` / `roa/fr`), pas la Belgique (`roa/fr-be`) ni la Suisse (`roa/fr-ch`).
- `_select_voice()` : priorité **France → FR → fallback**.
- Résultat : `Voix: French (France)` au lieu de "Afrikaans".

### 5. Fix TTS : sortie AUDIBLE sous WSL2 (commit `06f5807`) — le point clé

**Symptôme** : voix sélectionnée correcte mais **rien entendu** + erreurs `ALSA lib ... cannot find card '0'` + `aplay: audio open error`.

**Cause racine** : pyttsx3 (driver eSpeak) rend le texte dans un WAV temporaire, puis le joue via :
```python
os.system(f"aplay {temp_wav_name} -q")   # ALSA
```
`aplay` utilise **ALSA**, qui n'a **pas de carte son sous WSL2** → échec silencieux. `PULSE_SERVER` seul ne suffit PAS (il sert à `paplay`/`parecord`, eSpeak n'en tient pas compte).

**Fix** : `_write_asoundrc()` écrit `~/.asoundrc` qui redirige `pcm.!default`/`ctl.!default` vers le plugin `type pulse` (fourni par `libasound2-plugins`, installé par install.sh). Ainsi `aplay` **sans `-D`** passe par PulseAudio. Combiné à `PULSE_SERVER=tcp:<gateway>`, le son sort sur les hauts-parleurs Windows. Idempotent (n'écrit que si le fichier n'existe pas).

Testé manuellement : `aplay -D pulse` → retcode 0 ; `aplay` (via asoundrc) → retcode 0, plus d'erreurs.

**Leçon** : si TTS silencieux sous WSL2, vérifier dans l'ordre :
1. `~/.asoundrc` existe et contient `type pulse`
2. `PULSE_SERVER` est le gateway TCP (pas `unix:/mnt/wslg/...`)

## État runtime

- `PULSE_SERVER=tcp:172.17.192.1` (gateway WSL, dynamique)
- `~/.asoundrc` présent → ALSA redirigé vers PulseAudio
- Voix TTS : **French (France)**
- PulseAudio Windows : sink `waveout`, source `wavein` (`input_device=2` Jabra)

## Tests

- 28 passés, 5 skippés (Windows-only), 0 échoué
- ruff : All checks passed

## Nouveaux tests ajoutés (`tests/test_tts_sapi.py`)

- `test_is_french_sapi_hex`, `test_is_french_bcp47`
- `test_is_france_prefers_metropole`
- `test_write_asoundrc` (création + idempotence)

## Prochaines étapes

- [x] v0.7.0 : tests end-to-end (`tests/test_orchestrator.py`)
- [x] v0.7.0 : gestion des erreurs audio (timeout, device indisponible)
- [x] v0.7.0 : mode silencieux (`--silent` / `HAL_VOICE_SILENT`)
- [ ] v0.8.0 : wake word ("hal")

## Fichiers modifiés

- `src/hal_voice/adapters/tts.py` : `_is_french`, `_is_france`, `_select_voice` (France prioritaire), `_configure_pulse_for_espeak`, `_write_asoundrc`
- `tests/test_tts_sapi.py` : nouveaux tests
- `scripts/install.sh`, `scripts/uninstall.sh`, `scripts/setup.bat`, `scripts/teardown.bat`
- `requirements.txt`, `pyproject.toml`
- `docs/ROADMAP.md`, `AGENTS.md`
