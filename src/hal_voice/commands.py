"""
commands — Parser de commandes vocales pour Hal.

Analyse le texte transcrit par le STT et le convertit en intention
et paramètres pour être exécuté par le système.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Intent:
    """Représente une action à exécuter."""
    name: str
    params: dict[str, str] = field(default_factory=dict)


class CommandParser:
    """Analyse le texte pour en extraire des Intentions."""

    def __init__(self) -> None:
        # Mapping simple de mots-clés -> intentions
        # Pour une version plus évoluée, on pourrait utiliser des regex ou un petit NLP.
        self._triggers = {
            "stop": "STOP",
            "arrête": "STOP",
            "silence": "STOP",
            "bonjour": "GREETING",
            "salut": "GREETING",
            "au revoir": "EXIT",
            "quitte": "EXIT",
            "ferme": "EXIT",
            "lis": "READ_FILE",
            "lecture": "READ_FILE",
        }

    def parse(self, text: str) -> Intent | None:
        """
        Analyse le texte et renvoie une Intention si une commande est reconnue.
        Exemple: "lis notes.txt" -> Intent(name="READ_FILE", params={"filename": "notes.txt"})
        """
        if not text:
            return None

        text_lower = text.lower().strip()
        if not text_lower:
            return None

        # On détecte la première commande reconnue dans le texte,
        # ce qui permet aussi de gérer les déclencheurs multi-mots ("au revoir").
        best_index = -1
        best_phrase = ""
        best_intent: str | None = None
        for phrase, intent_name in self._triggers.items():
            index = text_lower.find(phrase)
            if index != -1 and (best_index == -1 or index < best_index):
                best_index = index
                best_phrase = phrase
                best_intent = intent_name

        if best_intent is None:
            return None

        if best_intent == "READ_FILE":
            # On prend tout ce qui suit la commande comme nom de fichier
            filename = text_lower[best_index + len(best_phrase):].strip()
            if not filename:
                return Intent(name="ERROR", params={"msg": "Quel fichier dois-je lire ?"})
            return Intent(name="READ_FILE", params={"filename": filename})

        return Intent(name=best_intent)


__all__ = ["CommandParser", "Intent"]
