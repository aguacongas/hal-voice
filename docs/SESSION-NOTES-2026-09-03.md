# Session notes — sauvegarde (2026-09-03)

## Objectif initial

Faire fonctionner la **capture micro** de `hal-voice` sous **WSL2** (le son sortait mais le micro ne captait rien).

## Diagnostic / cause racine

- `./scripts/run.sh` tournait mais la boucle `__main__.py` ne transcrivait jamais rien → **aucun son capté**.
- `python -m hal_voice --diagnose` (WSL) montrait : sources = `RDPSink.monitor` + `RDPSource`, aucun `alsa_input`/micro réel.
- **Cause 1 (structurelle) : WSLg ne ponte PAS le micro Windows.** La sortie audio passe (RDPSink → haut-parleurs Windows) mais `RDPSource` retourne du silence. Limite connue de WSLg.
- **Cause 2 (bug code audio_io.py) : `parecord` avec `--file-format=wav` vers `/dev/stdout` échoue** ("Failed to open audio file", 0 octets) sur le build PulseAudio Debian/Ubuntu de WSL. `parecord` n'a pas non plus d'option `--duration` ici → il enregistre à l'infini.

## Solution mise en place

### Sur Windows (hôte)
1. Installed **PulseAudio pour Windows** (build `pgaskin/pulseaudio-win32` v5) dans `%LOCALAPPDATA%\pulseaudio\pulseaudio`.
2. Config `%LOCALAPPDATA%\pulseaudio\pulseaudio\etc\halvoice.pa` :
   - `module-waveout sink_name=waveout source_name=wavein record=1 input_device=2` → expose le micro en source `wavein`
   - `module-native-protocol-tcp auth-anonymous=1` → écoute TCP port **4713** (accessible depuis WSL)
   - `--exit-idle-time=-1` pour ne pas s'arrêter quand inactif.
3. **Autostart au login** : raccourci dans `Shell:startup` → `start-pulse.vbs` → `start-pulse.cmd` (qui lance `pulseaudio.exe`).
4. Backup config : `halvoice.pa.bak`.

### Dans WSL2 (Ubuntu)
- **`~/.bashrc`** ajout ajouté : `export PULSE_SERVER="tcp:$(ip route show default | awk '{print $3}')"` (résolution dynamique de l'IP Windows).
- ⚠️ `.bashrc` n'est chargé que dans les shells **interactifs** ; `wsl.exe -- bash -lc` (non-interactif) ne le lit PAS → ne pas s'étonner si un script probe ne voit pas `PULSE_SERVER`.

### Dans le code (`src/hal_voice/audio_io.py`)
- **`_record_pulse` réécrit** : capture en **PCM brut s16le** vers un **fichier temporaire `.raw`** réel (≠ stdout/wav), timeout + gestion erreurs, conversion numpy directe (`np.fromfile`). C'était la cause du `max_amp=0`.
- `pulse_diagnostics()` ajoutée (mode `--diagnose`), appel via `__main__.py` quand `--diagnose` dans argv.

## Validation (marche à suivre aussi pour re-tester)

1. S'assurer que PulseAudio Windows tourne (processus `pulseaudio`, TCP 4713 en écoute).
2. Dans WSL (shell interactif) : `./scripts/run.sh --diagnose` → doit voir `wavein` et `max_amplitude` non nul quand on parle.
3. `python -m hal_voice.audio_io` (quick_test) → `max amplitude` > 100 si micro capte.
4. `./scripts/run.sh` → la boucle log `Audio capturé : ... max_amplitude=...` non nul.

Résultats constatés avec micro **Jabra** (`input_device=2`) : parecord direct jusqu'à ~32000, quick_test ~561 , boucle 243→2093→1500. Fichier brut s16le 16k mono OK.

## OUTSTANDING — travail restant

- **Objectif final non atteint : "marche sur n'importe quelle machine, quel que soit le micro/sortie".** La solution actuelle fige `input_device=2` (Jabra) dans `halvoice.pa` — **pas portable**.
- Investiguer une **détection auto du micro** :
  - Sans `input_device`, `module-waveout` capte l'index 0 (Microsoft casque) qui peut être muet et ne correspond PAS au micro par défaut Windows (default MMDevice était le micro Intel, index 1).
  - L'ordre des index WaveIn diffère du default MMDevice → mapping GUID→index nécessaire.
  - Tentative de détection par COM `MMDeviceEnumerator` : fiable via un **probe C# compilé** (`dotnet`, net8.0) dans `%LOCALAPPDATA%\pulseaudio\tools\micprobe.exe` qui retourne `DEFAULT_DEVICE_NAME` + liste `DEVICES_BEGIN`/`DEVICES_END` (GUID + nom + mfg). L'énumération `IMMDeviceCollection` a posé un blocage de cast COM (IID `0BD7A1BE-7A1A-44DB-8397-99E5398B8C8C`) — non résolu. `listmics.ps1` lit le registre MMDevices (`HKLM\...\MMDevices\Audio\Capture\<guid>\Properties`, props `{a45c254e...,2}`=nom, `...,24`=fabricant).
- Scripts de détection temporaires créés dans `%LOCALAPPDATA%\pulseaudio\` : `detect-mic.ps1`, `detect-mic2.ps1`, `detect-mic3.ps1`, `listmics.ps1`, `tools\micprobe*`. Source C# dans `C:\Users\LEFEBV~2\AppData\Local\Temp\opencode\micprobe\`.
- `AGENTS.md` mis à jour avec les commandes et tous les gotchas WSL2/PulseAudio (à lire avant de travailler).

## Fichiers modifiés pendant la session

- `src/hal_voice/audio_io.py` (réécriture `_record_pulse`, ajout `pulse_diagnostics`, log amplitude)
- `src/hal_voice/__main__.py` (mode `--diagnose`, import numpy, log `max_amplitude`)
- `AGENTS.md` (créé)

## Notes de dev pour continuer

- Ne PAS hardcoder un `input_device` fixe dans `halvoice.pa` pour un vrai usage portable.
- Test rapide d'un micro : `parecord --device=wavein --format=s16le --rate=16000 --channels=1 /tmp/x.raw` en shell interactif WSL (avec `PULSE_SERVER`), puis analyser avec `np.fromfile`.
- Le `.venv` WSL pointe sur `src` (éditable), donc pas de réinstallation après modif.
