"""
commands — Parser de commandes vocales pour Hal.

Analyse le texte transcrit par le STT et le convertit en intention
et paramètres pour être exécuté par le système.

Architecture :
    CommandParser.parse("lis notes.txt")
    → Intent(name="READ_FILE", params={"filename": "notes.txt"})

    CommandParser.parse("bonjour")
    → Intent(name="GREETING")

    CommandParser.parse("bla bla")
    → None (aucune commande reconnue)

Comment ça marche :
    1. Le texte est mis en minuscules et strip
    2. On cherche la première phrase déclencheur dans le dictionnaire
    3. Si c'est une commande avec paramètres (READ_FILE), on extrait le reste
    4. On retourne une Intent avec le nom et les paramètres

Extensions possibles :
    - Regex pour des patterns plus complexes
    - NLP (spaCy, etc.) pour comprendre les intentions naturelles
    - Contexte conversationnel (mémoire de la commande précédente)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Intent:
    """Représente une action à exécuter par le système.

    Attributes:
        name: Nom de l'intention (GREETING, STOP, EXIT, READ_FILE, ERROR)
        params: Paramètres de la commande (ex: {"filename": "notes.txt"})
    """
    name: str
    params: dict[str, str] = field(default_factory=dict)


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

        Exemples :
            "lis notes.txt" → Intent(name="READ_FILE", params={"filename": "notes.txt"})
            "bonjour" → Intent(name="GREETING")
            "bla bla" → None
        """
        if not text:
            return None

        text_lower = text.lower().strip()
        if not text_lower:
            return None

        # Cherche la première commande reconnue dans le texte.
        # On utilise find() pour gérer les déclencheurs multi-mots
        # (ex: "au revoir" se trouve après "bonjour" dans "bonjour, au revoir").
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

        # Pour READ_FILE, le nom de fichier est tout ce qui suit la commande
        if best_intent == "READ_FILE":
            filename = text_lower[best_index + len(best_phrase):].strip()
            if not filename:
                # Pas de fichier spécifié → retourne une erreur
                return Intent(name="ERROR", params={"msg": "Quel fichier dois-je lire ?"})
            return Intent(name="READ_FILE", params={"filename": filename})

        # Autres commandes : pas de paramètres
        return Intent(name=best_intent)


__all__ = ["CommandParser", "Intent"]
