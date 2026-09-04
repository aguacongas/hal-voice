"""
domain.protocols — Interfaces abstraites (Ports) de hal-voice.

Définissent les contrats que les adapters doivent implémenter.
Les use_cases dépendent uniquement de ces protocoles, jamais
des implémentations concrètes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class ISTT(Protocol):
    """Port pour la reconnaissance vocale (Speech-to-Text)."""

    def transcribe_array(self, audio: np.ndarray, sample_rate: int | None = None) -> str:
        """Transcrit un buffer audio en texte. Retourne "" si rien détecté."""
        ...


@runtime_checkable
class ITTS(Protocol):
    """Port pour la synthèse vocale (Text-to-Speech)."""

    def speak(self, text: str, blocking: bool = True) -> None:
        """Prononce le texte."""
        ...

    def stop(self) -> None:
        """Interrompt la parole en cours."""
        ...


@runtime_checkable
class IAudioCapture(Protocol):
    """Port pour la capture audio (micro)."""

    def record(self, duration_seconds: float) -> np.ndarray:
        """Capture audio pendant N secondes. Retourne un array int16 mono."""
        ...


@runtime_checkable
class IAudioPlayback(Protocol):
    """Port pour la lecture audio (haut-parleur)."""

    def play(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Joue un buffer audio. Bloquant jusqu'à la fin."""
        ...
