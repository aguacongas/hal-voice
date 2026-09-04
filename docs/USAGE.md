# Usage

> Guide d'utilisation de hal-voice.

## Lancement

### Linux / WSL2

```bash
./scripts/run.sh
```

### Directement avec Python

```bash
python -m hal_voice
```

### Mode silencieux

Sans synthèse vocale (le TTS reste muet, utile pour tester le STT sans
que la voix de Hal ne pollue l'écoute du micro) :

```bash
python -m hal_voice --silent
# ou
HAL_VOICE_SILENT=true python -m hal_voice
```

## Commandes vocales

hal-voice écoute pendant 3 secondes, transcrit la parole, puis exécute l'action correspondante.

### Commandes disponibles

| Commande | Exemple | Action |
|---|---|---|
| **Bonjour** / Salut | "bonjour" | Salut l'utilisateur |
| **Stop** / Arrête / Silence | "stop" | Coupe la parole en cours |
| **Au revoir** / Quitte / Ferme | "au revoir" | Quitte l'assistant |
| **Lis** / Lecture | "lis notes.txt" | Lit le contenu du fichier |

### Exemple de session

```
--- En attente d'une commande (3s) ---
Vous : bonjour
Hal [Intent] : GREETING {}
Hal: Bonjour Olivier. Que puis-je faire pour vous ?

--- En attente d'une commande (3s) ---
Vous : lis readme.md
Hal [Intent] : READ_FILE {'filename': 'readme.md'}
Hal: Lecture de readme.md. # hal-voice...

--- En attente d'une commande (3s) ---
Vous : au revoir
Hal [Intent] : EXIT {}
Hal: Au revoir.
```

## Diagnostic

### Diagnostic PulseAudio (WSL2)

```bash
python -m hal_voice --diagnose
```

Affiche :
- Le serveur PulseAudio détecté
- La liste des sources (micro, moniteurs, RDP)
- Le device sélectionné automatiquement
- Un test de capture de 3 secondes

### Test audio rapide

```bash
python -m hal_voice.audio_io
```

Enregistre 3 secondes et les relance. Utile pour vérifier que le micro fonctionne.

## Configuration

Tous les paramètres sont configurables via variables d'environnement :

| Variable | Défaut | Description |
|---|---|---|
| `HAL_VOICE_MODEL_PATH` | `models/vosk-model-small-fr-0.22` | Chemin vers le modèle Vosk |
| `HAL_VOICE_SAMPLE_RATE` | `16000` | Fréquence d'échantillonnage (Hz) |
| `HAL_VOICE_CHANNELS` | `1` | Nombre de canaux (1=mono) |
| `HAL_VOICE_DTYPE` | `int16` | Type de données audio |
| `HAL_VOICE_WAKE_WORD` | `hal` | Mot d'activation (placeholder) |
| `HAL_VOICE_SILENT` | `false` | `true` → désactive la synthèse vocale (équivaut à `--silent`) |

Exemple :

```bash
export HAL_VOICE_MODEL_PATH=/chemin/vers/autre/modele
python -m hal_voice
```

## Tests

```bash
# Tous les tests
pytest

# Tests unitaires uniquement (pas de matériel)
pytest -m "not requires_hardware"

# Tests avec verbose
pytest tests/test_commands.py -v
```

## Ajouter une commande

1. Éditer `src/hal_voice/use_cases/command_parser.py`
2. Ajouter un mot-clé dans le mapping des triggers
3. Ajouter le handler dans `src/hal_voice/use_cases/orchestrator.py` (`execute_intent`)
4. Ajouter un test dans `tests/test_commands.py` (parser) et éventuellement `tests/test_orchestrator.py` (exécution)
