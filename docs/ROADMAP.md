# Roadmap

## v0.1.0 — Squelette ✅
- [x] Création du repo GitHub
- [x] Choix de licence : Apache 2.0
- [x] Structure de dossiers
- [x] Fichiers racine : `README.md`, `LICENSE`, `THIRD-PARTY-NOTICES`, `.gitignore`, `requirements.txt`, `pyproject.toml`
- [x] Modules vides (placeholders)

## v0.2.0 — Premier module audible ✅
- [x] `audio_io.py` : capture micro + lecture WAV
- [x] Test manuel : enregistrement + relecture
- [x] Documentation des devices audio trouvés
- [x] Tests pytest

## v0.3.0 — STT (Vosk FR) ✅
- [x] `stt_vosk.py` : transcription offline
- [x] `config.py` : centralisation des chemins / sample rate / env
- [x] Modèle `vosk-model-small-fr-0.22` téléchargé dans `models/`
- [x] Smoke test micro → STT validé
- [x] Tests pytest (5 verts)

## v0.4.0 — TTS (SAPI) ✅
- [x] `tts_sapi.py` : synthèse vocale FR via SAPI 5
- [x] Auto-sélection voix FR (Hortense sur Windows 11)
- [x] Smoke test : « Bonjour, je suis Hal » entendu
- [x] Tests pytest (9 verts, dont 1 hardware)

## v0.5.0 — Commandes vocales ✅
- [x] `commands.py` : parser de commandes ("lis <fichier>", "stop", "au revoir", etc.)
- [x] Intégration STT → commande → TTS
- [x] `__main__.py` : boucle principale interactive
- [x] `--diagnose` : diagnostic PulseAudio (WSL2)
- [x] Tests pytest (27+ verts)

## v0.6.0 — WSL2 + Cross-platform ✅
- [x] Détection automatique WSL2 (`/proc/version`)
- [x] PulseAudio Windows (TCP 4713) comme backend audio
- [x] `tts_sapi.py` multi-plateforme (SAPI5 + pyttsx3)
- [x] `hotkey.py` : raccourcis clavier globaux via pynput
- [x] `scripts/run.sh` : auto-start PulseAudio Windows
- [x] `scripts/detect-mic.ps1` : détection auto du micro WaveIn
- [x] Auto-detection du device d'entrée par amplitude (`_test_source_amplitude`)
- [x] Fix double `module-waveout` (commenter dans `default.pa`)
- [x] Fix `_record_pulse` shape `(n,1)` compatible sounddevice
- [x] Commentaires détaillés en français sur tout le code
- [x] Documentation complète (README, ARCHITECTURE, INSTALL, USAGE)

## v0.7.0 — App utilisable
- [ ] `scripts/install.sh` amélioré (détection auto des dépendances)
- [ ] Tests end-to-end
- [ ] Gestion des erreurs audio (timeout, device indisponible)
- [ ] Mode silencieux (pas de TTS)

## v0.8.0 — Wake word
- [ ] `wakeword.py` : détection du mot-clé "hal"
- [ ] Seuillage adaptatif
- [ ] Mode veille (écoute basse consommation)

## v0.9.0 — Enrichissements
- [ ] Commandes supplémentaires (météo, calcul, etc.)
- [ ] Contexte conversationnel (mémoire)
- [ ] Configuration via fichier YAML/TOML
- [ ] Logging structuré

## v1.0.0 — Release
- [ ] Doc complète
- [ ] Tests > 80% couverture
- [ ] Tag `v1.0.0` sur GitHub
- [ ] CI/CD (GitHub Actions)
