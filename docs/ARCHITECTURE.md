# Architecture

> Architecture technique de hal-voice — assistant vocal 100% local.

## Vue d'ensemble

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Micro      │───▶│  Audio I/O  │───▶│  STT Vosk   │
│  (capture)   │    │ (audio_io)  │    │ (stt_vosk)  │
└─────────────┘    └──────┬──────┘    └──────┬──────┘
                          │                   │
                          │    ┌──────────────┘
                          │    │
                          ▼    ▼
                   ┌─────────────────┐
                   │  Command Parser │
                   │   (commands)    │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Action Handler │
                   │ (__main__.py)   │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   TTS SAPI5     │───▶ Haut-parleur
                   │  (tts_sapi)     │
                   └─────────────────┘
```

## Modules

### `audio_io.py` — Capture micro + lecture audio

Le module le plus complexe. Gère deux backends :

| Backend | Plateforme | Input | Output |
|---|---|---|---|
| `sounddevice` (PortAudio) | Windows natif | `sd.rec()` | `sd.play()` |
| PulseAudio CLI | WSL2 | `parecord` → fichier `.raw` → numpy | `paplay` ← fichier `.wav` temp |

**Détection WSL2** : `"microsoft" in /proc/version`

**Priorité PulseAudio** :
1. PulseAudio Windows (TCP 4713) — vrai micro via `module-waveout`
2. WSLg (unix socket) — micro virtuel RDP, silence

**Auto-detection du device** : `_pulse_find_input_device()` probe chaque source avec `_test_source_amplitude()` (~1s chacune) et choisit celle avec la meilleure amplitude.

### `stt_vosk.py` — Speech-to-Text

- Modèle Vosk FR small (~40 Mo, offline)
- Lazy loading : modèle chargé au premier appel de `transcribe_array()`
- Accepte float ou int16, mono ou stereo (conversion automatique)
- Format de sortie : texte en minuscules

### `tts_sapi.py` — Text-to-Speech

Deux backends selon la plateforme :

| Backend | Plateforme | Dépendance |
|---|---|---|
| `_SapiBackend` | Windows | `win32com` (SAPI 5, intégré) |
| `_Pyttsx3Backend` | Linux/WSL | `pyttsx3` + `espeak-ng` |

Sélection automatique de la voix française.

### `commands.py` — Parser de commandes

Mapping simple mots-clés → intentions :

| Mot-clé | Intention | Action |
|---|---|---|
| bonjour, salut | GREETING | Salut l'utilisateur |
| stop, arrête, silence | STOP | Coupe la parole |
| au revoir, quitte, ferme | EXIT | Quitte l'assistant |
| lis, lecture | READ_FILE | Lit un fichier à voix haute |

### `config.py` — Configuration

Tous les paramètres via variables d'environnement (`HAL_VOICE_*`). Dataclass immutable `Config` créée via `Config.from_env()`.

### `hotkey.py` — Raccourcis clavier

Via `pynput` (cross-platform). Thread daemon en arrière-plan.

### `__main__.py` — Boucle principale

```
Boucle:
  1. Capture 3s d'audio
  2. Transcription (Vosk)
  3. Parsing (CommandParser)
  4. Exécution de l'intention
  5. Réponse TTS
```

## Scripts

| Script | Plateforme | Usage |
|---|---|---|
| `scripts/install.bat` | Windows | Installation (venv + deps + modèle Vosk) |
| `scripts/install.sh` | Linux/WSL | Installation (apt + venv + deps + modèle Vosk) |
| `scripts/run.bat` | Windows | Lancement |
| `scripts/run.sh` | Linux/WSL | Lancement (auto-start PulseAudio Windows) |
| `scripts/detect-mic.ps1` | Windows | Détection automatique du micro WaveIn |
| `scripts/test-mic-device.sh` | WSL | Test d'amplitude d'un device PulseAudio |

## Flux audio WSL2

```
Windows:  Micro → module-waveout → PulseAudio (TCP 4713)
                                     │
WSL2:                              parecord → /tmp/*.raw → numpy int16 → Vosk
```

## Pièges connus

1. `parecord` n'a pas de `--duration` → poll + terminate
2. `/dev/stdout` ne marche pas → fichier `.raw` temporaire
3. `module-waveout` nécessite `input_device=<index>` explicite
4. `default.pa` peut charger un double `module-waveout` → commenter
5. PID file stale → "Daemon already running" → supprimer le runtime dir
6. `Get-NetRoute` PowerShell peut retourner la mauvaise IP → utiliser `ip route show default` depuis WSL
