"""
use_cases.command_parser — Analyse du texte transcrit pour extraire une intention.

Use case pur : prend un texte en entrée, retourne une Intent.
Pas de dépendance aux adapters (pas de STT, pas de TTS).

Architecture :
    CommandParser.parse("lis notes.txt")
    → Intent(name="READ_FILE", params={"filename": "notes.txt"})

    CommandParser.parse("bonjour")
    → Intent(name="GREETING")

    CommandParser.parse("bla bla")
    → None (aucune commande reconnue)
"""

from __future__ import annotations

from hal_voice.domain.entities import Intent


class CommandParser:
    """Analyse le texte pour en extraire des Intentions.

    Utilise un dictionnaire de mots-clés → intentions.
    Supporte les commandes multi-mots ("au revoir") et les paramètres
    extraits du texte (nom de fichier pour READ_FILE).
    """

    def __init__(self) -> None:
        # Mapping simple de mots-clés → intentions.
        # Les clés sont en minuscules. Les commandes multi-mots
        # (comme "au revoir") sont supportées via str.find().
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
        """Analyse le texte et renvoie une Intention si une commande est reconnue.

        Algorithme :
            1. Normalise le texte (minuscules, strip)
            2. Pour chaque phrase déclencheur, cherche sa position dans le texte
            3. Retourne la première commande trouvée (la plus tôt dans le texte)
            4. Pour READ_FILE, extrait le nom de fichier après la commande
        """
        if not text:
            return None

        text_lower = text.lower().strip()
        if not text_lower:
            return None

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
            filename = text_lower[best_index + len(best_phrase) :].strip()
            if not filename:
                return Intent(name="ERROR", params={"msg": "Quel fichier dois-je lire ?"})
            return Intent(name="READ_FILE", params={"filename": filename})

        return Intent(name=best_intent)
