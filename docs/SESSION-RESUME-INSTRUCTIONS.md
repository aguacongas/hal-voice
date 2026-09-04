# Redémarrage de session hal-voice — instructions

## Contexte

Projet en Clean Architecture (`domain/`, `use_cases/`, `adapters/`) sur branche `wsl2-support`. Depuis 2026-09-05, le **TTS est audible sous WSL2** (voix French (France) via PulseAudio Windows). Installation/uninstallation automatisées. **Pas de back-compat** avec les anciens modules.

## Conclusion du travail déjà fait (à ne pas refaire)

- **Clean Architecture** : `adapters/`, `use_cases/`, `domain/` — plus de modules legacy à plat.
- **Scripts d'installation** : `install.sh`, `uninstall.sh`, `setup.bat`, `teardown.bat`.
- **Auto-detection du micro** : `_pulse_find_input_device()` probe chaque source et choisit celle qui capte.
- **Fix double module-waveout** : ligne commentée dans `default.pa`.
- **run.sh auto-start PulseAudio Windows** si pas accessible.
- **TTS audible WSL2** : `~/.asoundrc` → PulseAudio + `PULSE_SERVER=tcp:<gateway>` + voix French (France).

## TOUT RELIRE AVANT DE CODER

1. `AGENTS.md`
2. `docs/SESSION-NOTES-2026-09-04.md`
3. `docs/SESSION-NOTES-2026-09-05.md`
4. `docs/ARCHITECTURE.md`

## État runtime (à vérifier/rétablir d'abord)

### 1. Vérifier PulseAudio Windows tourne (hôte Windows)

```powershell
Get-Process -Name pulseaudio
netstat -ano | Select-String ":4713"     # doit être LISTENING
```

- Si absent : `run.sh` le lance automatiquement, ou manuellement :
  ```powershell
  Start-Process -FilePath "$env:LOCALAPPDATA\pulseaudio\pulseaudio\bin\pulseaudio.exe" -ArgumentList "-F", "$env:LOCALAPPDATA\pulseaudio\pulseaudio\etc\halvoice.pa" -WindowStyle Hidden
  ```
- Si "Daemon already running" :
  ```powershell
  Remove-Item "$env:USERPROFILE\.config\pulse\*-runtime\pid" -Force
  ```

### 2. Vérifier la config micro

`%LOCALAPPDATA%\pulseaudio\pulseaudio\etc\halvoice.pa` doit contenir :
```
load-module module-waveout sink_name=waveout source_name=wavein record=1 input_device=2
```

`%LOCALAPPDATA%\pulseaudio\pulseaudio\etc\pulse\default.pa` doit avoir la ligne `module-waveout` **commentée** :
```
#load-module module-waveout sink_name=waveout source_name=wavein
```

### 3. Vérifier WSL (audio entrée ET sortie)

```bash
# IP Windows
ip route show default | awk '{print $3}'    # 172.x.x.x

# PulseAudio accessible
export PULSE_SERVER=tcp:$(ip route show default | awk '{print $3}')
pactl info | grep "Server Name"             # "pulseaudio"

# TTS audible : ~/.asoundrc doit exister avec 'type pulse'
cat ~/.asoundrc
```

## Validation TTS (important après tout doute sur l'audio)

```bash
# Depuis WSL (shell interactif)
source .venv/bin/activate
python -c "from hal_voice.adapters.tts import TTS,_configure_pulse_for_espeak; _configure_pulse_for_espeak(); t=TTS(); print('Voix:', t.voice_name); t.speak('Bonjour, je suis Hal')"
```
Doit afficher `Voix: French (France)`, aucun `ALSA lib ... cannot find card`, et **on doit entendre** la voix sur les haut-parleurs Windows (sink `waveout`).

## Test rapide de capture

```bash
# Depuis WSL (shell interactif)
./scripts/run.sh --diagnose          # max_amplitude > 100 quand on parle
./scripts/run.sh                     # boucle vocale interactive
```

## Commandes utiles

| Commande | Plateforme | Usage |
|---|---|---|
| `./scripts/run.sh` | WSL | Lance l'assistant (auto-start PulseAudio) |
| `./scripts/run.sh --diagnose` | WSL | Diagnostic PulseAudio |
| `python -m hal_voice --diagnose` | WSL | Idem (direct) |
| `pytest -q` | WSL | Tests unitaires (envoie via `wsl.exe -d Ubuntu -- bash -c`) |
| `ruff check src tests` | WSL | Lint (limite 100 cols) |
| `.\scripts\setup.bat` | Windows | Installation complète WSL2 + Ubuntu + PulseAudio |
| `.\scripts\teardown.bat` | Windows | Désinstallation |

> **Note exécution WSL depuis Windows** : utiliser `wsl.exe -d Ubuntu -- bash -c "..."` (distro Ubuntu, pas `*`). `wsl.exe -- bash -lc` (non-interactif) n'active PAS `.bashrc`, donc pas de `PULSE_SERVER` en variables d'env globales. Le code fixe lui-même `PULSE_SERVER` avant pyttsx3.

## Branches Git

- `main` : code stable
- `wsl2-support` : travail en cours (Clean Architecture + WSL2)

## Prochaines étapes

- v0.7.0 : tests end-to-end, gestion des erreurs audio, mode silencieux (`--silent`)
- v0.8.0 : wake word ("hal")
- v0.9.0 : commandes supplémentaires, contexte conversationnel
- v1.0.0 : CI/CD, couverture tests > 80%
