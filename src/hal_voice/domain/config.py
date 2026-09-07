"""
domain.config — Paramètres globaux de hal-voice (entité pure).

Centralise les constantes et le dataclass Config.
Aucune dépendance externe (pas d'os, pas de pathlib以外).

Constants :
    PROJECT_ROOT     : racine du projet (parent de src/)
    MODELS_DIR       : dossier contenant les modèles Vosk
    DEFAULT_*        : valeurs par défaut pour tous les paramètres

Config :
    Dataclass immutable (frozen) des paramètres runtime.
    Le chargement depuis les variables d'environnement se fait
    dans adapters.config_loader (pas ici).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Racine du projet : remonte de src/hal_voice/domain/ vers la racine
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Dossier des modèles Vosk (gitignored)
MODELS_DIR = PROJECT_ROOT / "models"

# ── Modèle Vosk par défaut ────────────────────────────────────────────
# Modèle LINTO (français, AGPL) : bien plus précis que le "small" pour les
# commandes françaises, et plus rapide que le "fr-0.22" (~0.4xRT). Le
# "small" était trop imprécis; le "fr-0.22" trop lent. Remplaçable via
# HAL_VOICE_MODEL_PATH.
DEFAULT_VOSK_MODEL_NAME = "vosk-model-fr-0.6-linto-2.2.0"
DEFAULT_VOSK_MODEL_PATH = MODELS_DIR / DEFAULT_VOSK_MODEL_NAME

# ── Paramètres audio par défaut ───────────────────────────────────────
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
DEFAULT_DTYPE = "int16"

# ── Voix TTS par défaut ───────────────────────────────────────────────
DEFAULT_TTS_VOICE_NAME_HINT = "fr"

# ── Wake word (mot d'activation) ──────────────────────────────────────
DEFAULT_WAKE_WORD = "hal"
# Variantes phonétiques acceptées pour le wake word. Vosk ne reconnaît
# pas toujours un mot court hors lexique ("hal" → "al", "ah", "allez"...).
# On accepte ces tokens comme équivalents. Remplaçable via
# HAL_VOICE_WAKE_WORD_VARIANTS (liste séparée par des virgules).
DEFAULT_WAKE_WORD_VARIANTS = ("al", "ah", "allez", "à")


@dataclass(frozen=True)
class Config:
    """Snapshot immutable des paramètres runtime.

    ``frozen=True`` empêche la modification accidentelle après création.
    """

    vosk_model_path: Path
    sample_rate: int
    channels: int
    dtype: str
    wake_word: str
    wake_word_variants: tuple[str, ...] = DEFAULT_WAKE_WORD_VARIANTS
    silent: bool = False
