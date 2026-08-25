# Roadmap

## v0.1.0 — Squelette ✅
- [x] Création du repo GitHub
- [x] Choix de licence : Apache 2.0
- [x] Structure de dossiers
- [x] Fichiers racine : `README.md`, `LICENSE`, `THIRD-PARTY-NOTICES`, `.gitignore`, `requirements.txt`, `pyproject.toml`
- [x] Modules vides (placeholders)

## v0.2.0 — Premier module audible
- [ ] `audio_io.py` : capture micro + lecture WAV
- [ ] Test manuel : enregistrement + relecture
- [ ] Documentation des devices audio trouvés

## v0.3.0 — STT (Vosk FR) ✅
- [x] `stt_vosk.py` : transcription offline
- [x] `config.py` : centralisation des chemins / sample rate / env
- [x] Modèle `vosk-model-small-fr-0.22` téléchargé dans `models/`
- [x] Smoke test micro → STT validé (« ça va »)
- [x] Tests pytest (5 verts)

## v0.4.0 — TTS (SAPI) ✅
- [x] `tts_sapi.py` : synthèse vocale FR via `System.Speech` (SAPI 5)
- [x] Auto-sélection voix FR (Hortense sur Windows 11)
- [x] Smoke test : « Bonjour, je suis Hal » entendu
- [x] Tests pytest (9 verts, dont 1 hardware)

## v0.5.0 — Commandes vocales
- [ ] `commands.py` : parser de commandes ("lis <fichier>", "stop", etc.)
- [ ] Intégration STT → commande → TTS

## v0.6.0 — Wake word + hotkey
- [ ] `wakeword.py` : détection du mot-clé "hal"
- [ ] `hotkey.py` : raccourci global Windows (ex. `F8`)

## v0.7.0 — App utilisable
- [ ] `__main__.py` : boucle principale
- [ ] `scripts/install.bat` + `scripts/run.bat`
- [ ] Tests end-to-end

## v1.0.0 — Release
- [ ] Doc complète (`docs/`)
- [ ] Tests > 80 % couverture
- [ ] Tag `v1.0.0` sur GitHub
