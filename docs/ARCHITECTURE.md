# Architecture

> Architecture technique de hal-voice — assistant vocal 100% local.
> **Clean Architecture** : `domain/` (entités + protocoles + config), `use_cases/` (logique métier), `adapters/` (implémentations concrètes).

## Vue d'ensemble

```
                     ┌──────────────────────────┐
                     │       __main__.py        │  (DI : wiring)
                     │  Orchestrator + adapters │
                     └───────────┬──────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │          use_cases/                 │
              │     Orchestrator, CommandParser     │  (dépend des protocoles)
              └──────────────────┬──────────────────┘
                                 │
   ┌──────────────┬──────────────┼──────────────┬─────────────┐
   │              │              │              │             │
   ▼              ▼              ▼              ▼             ▼
 domain/       adapters/      adapters/      adapters/     adapters/
 protocols   audio_io.py     stt_vosk.py      tts.py       hotkey.py
 (ISTT,       (capture/       (Speech-to-    (Text-to-     (raccourcis
 ITTS,          lecure)         Text)         Speech)       clavier)
 IAudio*)
```

Flux logique : `Micro → IAudioCapture → ISTT → Intent → Orchestrator → ITTS → Haut-parleur`.
L'`Orchestrator` ne connaît que les **protocoles** (`domain/protocols.py`) ; les adapters concrets sont injectés depuis `__main__.py`.

## Packages

### `domain/` — Cœur (sans dépendances externes)

| Fichier | Contenu |
|---|---|
| `entities.py` | `Intent` (intention + texte + données) |
| `protocols.py` | `ISTT`, `ITTS`, `IAudioCapture`, `IAudioPlayback` (ABC) |
| `config.py` | `Config` (dataclass frozen) + constantes (langues, chemins) |

### `use_cases/` — Logique métier

| Fichier | Rôle |
|---|---|
| `command_parser.py` | Mapping mots-clés → `Intent` |
| `orchestrator.py` | Pilote la boucle STT→Intent→Action→TTS, via les protocoles |

### `adapters/` — Implémentations concrètes

| Fichier | Rôle |
|---|---|
| `config_loader.py` | `load_config_from_env()` → `Config` |
| `audio_io.py` | Capture micro + lecture audio (PulseAudio CLI) |
| `stt_vosk.py` | Vosk offline (modèle FR small, lazy loading) |
| `tts.py` | pyttsx3+eSpeak-ng (Linux/WSL) |
| `hotkey.py` | Raccourcis clavier via pynput |

## `adapters/audio_io.py` — Capture micro + lecture audio

Le module le plus complexe. Cible : Linux/WSL2 uniquement, via PulseAudio.

| Input | Output |
|---|---|
| `parecord` → fichier `.raw` → numpy | `paplay` ← fichier `.wav` temp |

Le backend natif `sounddevice` a été retiré (plus de support Windows natif).

**Détection WSL2** : `"microsoft" in /proc/version`

**Priorité PulseAudio** :
1. PulseAudio Windows (TCP 4713) — vrai micro via `module-waveout`
2. WSLg (unix socket) — micro virtuel RDP, silence

**Auto-detection du device** : `_pulse_find_input_device()` probe chaque source avec `_test_source_amplitude()` (~1s chacune) et choisit celle avec la meilleure amplitude.

## `adapters/stt_vosk.py` — Speech-to-Text

- Modèle Vosk FR small (~40 Mo, offline)
- Lazy loading : modèle chargé au premier appel de `transcribe_array()`
- Accepte float ou int16, mono ou stereo (conversion automatique)
- Format de sortie : texte en minuscules

## `adapters/tts.py` — Text-to-Speech

Backend unique :

| Backend | Dépendance |
|---|---|
| `_Pyttsx3Backend` | `pyttsx3` + `espeak-ng` |

Le backend Windows SAPI 5 (`win32com`) a été retiré.

**Sélection de voix** (`_select_voice`) — priorité :
1. `French (France)` (`_is_france` : hex `40C` / `roa/fr`)
2. n'importe quel FR (`_is_french` : `fr`, `fra`, `roa/fr-be`, …)
3. fallback première voix

**Sortie audible sous WSL2** — voir § "Pièges connus" #7 : pyttsx3/eSpeak joue via `aplay` (ALSA), donc `_configure_pulse_for_espeak()` :
1. force `PULSE_SERVER=tcp:<gateway>` (Windows) vérifié via `pactl info`
2. `_write_asoundrc()` écrit `~/.asoundrc` (`pcm.!default` → `type pulse`) pour que `aplay` passe par PulseAudio

## `use_cases/command_parser.py` — Parser de commandes

Mapping simple mots-clés → intentions :

| Mot-clé | Intention | Action |
|---|---|---|
| bonjour, salut | GREETING | Salut l'utilisateur |
| stop, arrête, silence | STOP | Coupe la parole |
| au revoir, quitte, ferme | EXIT | Quitte l'assistant |
| lis, lecture | READ_FILE | Lit un fichier à voix haute |

## `scripts/` — Installation / Lancement

| Script | Plateforme | Usage |
|---|---|---|
| `install.sh` | Linux/WSL | Auto-install Python + deps système + venv + modèle Vosk (multi-distro, `--check`) |
| `uninstall.sh` | Linux/WSL | Désinstallation (safe ; `--full` retire les paquets apt) |
| `setup.bat` | Windows (hôte) | Installe WSL2 + Ubuntu + PulseAudio + configure + lance install.sh |
| `teardown.bat` | Windows (hôte) | Désinstallation (safe ; `--full` retire WSL2 + Ubuntu) |
| `run.sh` | Linux/WSL | Lancement (auto-start PulseAudio Windows) |

## Flux audio WSL2

```
Windows:  Micro → module-waveout → PulseAudio (TCP 4713)
                                      │
WSL2:                              parecord → /tmp/*.raw → numpy int16 → Vosk
Sortie TTS WSL2:  eSpeak → WAV temp → aplay (via ~/.asoundrc → pulse) → Haut-parleurs Windows
```

## Pièges connus

1. `parecord` n'a pas de `--duration` → poll + terminate
2. `/dev/stdout` ne marche pas → fichier `.raw` temporaire
3. `module-waveout` nécessite `input_device=<index>` explicite
4. `default.pa` peut charger un double `module-waveout` → commenter
5. PID file stale → "Daemon already running" → supprimer le runtime dir
6. `Get-NetRoute` PowerShell peut retourner la mauvaise IP → utiliser `ip route show default` depuis WSL
7. **TTS silencieux WSL2** : pyttsx3/eSpeak joue via `aplay` (ALSA), sans carte son sous WSL2 → erreurs + silence. Fix : `~/.asoundrc` (`pcm.!default` → `type pulse`, nécessite `libasound2-plugins`) + `PULSE_SERVER=tcp:<gateway>`. `PULSE_SERVER` seul ne suffit PAS.
8. **Voix "Afrikaans"** : `_lang_id_to_int` ne gère que l'hex SAPI ; les tags BCP 47 (`roa/fr`) ne parse pas → `_is_french`/`_is_france` traitent la string directement.
