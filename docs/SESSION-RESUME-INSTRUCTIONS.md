# Redémarrage de session hal-voice — instructions

## Contexte

Session 2026-09-04 : auto-detection du micro, fix double module-waveout, commentaires sur tout le code, documentation complète. **Le micro fonctionne automatiquement** sous WSL2 via PulseAudio Windows.

## Conclusion du travail déjà fait (à ne pas refaire)

- **Auto-detection du device** : `_pulse_find_input_device()` probe chaque source PulseAudio et choisit celle qui capte vraiment.
- **Fix double module-waveout** : ligne commentée dans `default.pa`.
- **run.sh auto-start PulseAudio Windows** si pas accessible.
- **detect-mic.ps1** : détection brute-force du bon index WaveIn.
- Tout le code commenté en français, documentation à jour.

## TOUT RELIRE AVANT DE CODER

1. `AGENTS.md`
2. `docs/SESSION-NOTES-2026-09-04.md`
3. `docs/ARCHITECTURE.md`

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

### 3. Vérifier WSL

```bash
# IP Windows
ip route show default | awk '{print $3}'
# Doit retourner 172.x.x.x

# PulseAudio accessible
export PULSE_SERVER=tcp:$(ip route show default | awk '{print $3}')
pactl info | grep "Server Name"
# Doit retourner "pulseaudio"
```

## Test rapide de capture

```bash
# Depuis WSL (shell interactif)
./scripts/run.sh --diagnose          # max_amplitude > 100 quand on parle
python -m hal_voice.audio_io         # quick_test : max amplitude > 100
./scripts/run.sh                     # boucle vocale interactive
```

## Commandes utiles

| Commande | Plateforme | Usage |
|---|---|---|
| `./scripts/run.sh` | WSL | Lance l'assistant (auto-start PulseAudio) |
| `./scripts/run.sh --diagnose` | WSL | Diagnostic PulseAudio |
| `python -m hal_voice --diagnose` | WSL | Idem (direct) |
| `python -m hal_voice.audio_io` | WSL | Test audio record/replay |
| `pytest -q` | WSL | Tests unitaires |
| `.\scripts\detect-mic.ps1` | Windows | Détection auto du micro WaveIn |

## Branches Git

- `main` : code stable
- `wsl2-support` : travail WSL2 (5 commits)

## Prochaines étapes

- v0.7.0 : gestion des erreurs audio, mode silencieux
- v0.8.0 : wake word ("hal")
- v0.9.0 : commandes supplémentaires, contexte conversationnel
- v1.0.0 : CI/CD, couverture tests > 80%
