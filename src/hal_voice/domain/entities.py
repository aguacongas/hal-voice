"""
domain.entities — Entités pures de hal-voice.

Pas de dépendances externes, pas de logique métier complexe.
Juste des dataclasses qui représentent les concepts du domaine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Intent:
    """Action à exécuter par le système, issue de l'analyse du texte transcrit.

    Attributes:
        name: Nom de l'intention (GREETING, STOP, EXIT, READ_FILE, ERROR)
        params: Paramètres de la commande (ex: {"filename": "notes.txt"})
    """

    name: str
    params: dict[str, str] = field(default_factory=dict)
