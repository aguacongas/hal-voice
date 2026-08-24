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

## v0.3.0 — STT (Vosk FR)
- [ ] `stt_vosk.py` : transcription offline
- [ ] Script de téléchargement du modèle FR (`scripts/download_vosk_model.py`)
- [ ] Test : dictée → texte

## v0.4.0 — TTS (SAPI)
- [ ] `tts_sapi.py` : synthèse vocale FR via `System.Speech`
- [ ] Test : texte → voix

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
