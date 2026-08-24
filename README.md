# hal-voice

> Interface vocale 100% locale pour Windows.
> **STT** (voix → texte) via [Vosk](https://alphacephei.com/vosk/) (offline, FR).
> **TTS** (texte → voix) via SAPI 5 (`System.Speech`, intégré à Windows).
> Pas de cloud, pas de clé d'API, pas d'écoute permanente.

## 🎯 Objectif

Donner la parole et l'ouïe à un assistant local sur Windows, en français, sans dépendre d'un service cloud. Pensé pour un usage personnel (dictée, relecture de textes, commandes vocales).

## ✨ Fonctionnalités prévues

| Mode | Description |
|---|---|
| **Dictée** | Tu parles, hal-voice transcrit en texte (FR, offline). |
| **Relecture** | hal-voice lit à voix haute un fichier / une scène. |
| **Commande vocale** | Mot-clé (ex. « hal ») + phrase → action. |
| **Hotkey global** | Touche dédiée (ex. `F8`) pour activer / couper le micro. |

## 🚧 Statut

**v0.1.0 — Squelette.** Aucun module implémenté, juste la structure du projet. Le code arrive par étapes (voir `docs/ROADMAP.md`).

## 📦 Stack technique

- **Langage** : Python 3.10+
- **STT** : [`vosk`](https://pypi.org/project/vosk/) + modèle `vosk-model-small-fr-0.22`
- **TTS** : `System.Speech` (SAPI 5, via `pywin32`)
- **Audio** : `sounddevice`, `soundfile`
- **Hotkey** : `keyboard` (Windows)
- **Config** : `pyyaml`

## 📁 Structure

```
hal-voice/
├── src/hal_voice/        ← code source (modules)
├── tests/                ← tests unitaires
├── docs/                 ← ARCHITECTURE.md, INSTALL.md, USAGE.md, ROADMAP.md
├── scripts/              ← install.bat, run.bat (Windows)
├── requirements.txt
├── pyproject.toml
├── LICENSE               ← Apache 2.0
└── THIRD-PARTY-NOTICES   ← licences des dépendances
```

## 🛠️ Installation (à venir)

```bash
git clone https://github.com/aguacongas/hal-voice.git
cd hal-voice
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Le téléchargement du modèle Vosk FR sera automatisé par `scripts/install.bat`.

## 📜 Licence

**Apache License 2.0** — voir [LICENSE](LICENSE).

Les dépendances tierces ont leurs propres licences, listées dans [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES).

## 👤 Auteur

Olivier Lefebvre — [@aguacongas](https://github.com/aguacongas)
