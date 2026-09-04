"""
Tests du parser de commandes vocales (commands.py).

Ces tests vérifient que le parser reconnaît correctement les intentions
depuis le texte transcrit par le STT. Pas de dépendance matérielle.
"""

from __future__ import annotations

from hal_voice.commands import CommandParser, Intent


def test_parse_empty_returns_none() -> None:
    """Texte vide ou whitespace → None."""
    assert CommandParser().parse("") is None
    assert CommandParser().parse("   ") is None
    assert CommandParser().parse(None) is None  # type: ignore[arg-type]


def test_parse_unknown_text_returns_none() -> None:
    """Texte non reconnu → None."""
    assert CommandParser().parse("bla bla bla") is None


def test_parse_greeting() -> None:
    """Le mot 'bonjour' déclenche l'intention GREETING."""
    intent = CommandParser().parse("bonjour")
    assert intent == Intent(name="GREETING")
    assert intent is not None and intent.params == {}


def test_parse_greeting_ignores_case_and_whitespace() -> None:
    """Le parser est insensible à la casse et au whitespace."""
    intent = CommandParser().parse("  SALUT  ")
    assert intent == Intent(name="GREETING")


def test_parse_stop_synonyms() -> None:
    """Plusieurs synonymes déclenchent STOP."""
    for text in ("stop", "arrête", "silence"):
        assert CommandParser().parse(text) == Intent(name="STOP")


def test_parse_exit_synonyms() -> None:
    """Plusieurs synonymes déclenchent EXIT."""
    for text in ("au revoir", "quitte", "ferme"):
        assert CommandParser().parse(text) == Intent(name="EXIT")


def test_parse_multiword_trigger_embedded_in_sentence() -> None:
    """Un déclencheur multi-mots ('au revoir') dans une phrase plus longue."""
    intent = CommandParser().parse("bonjour, au revoir")
    # 'bonjour' est trouvé en premier (index plus petit)
    assert intent == Intent(name="GREETING")


def test_parse_read_file_with_filename() -> None:
    """'lis notes.txt' → Intent READ_FILE avec le nom de fichier."""
    intent = CommandParser().parse("lis notes.txt")
    assert intent == Intent(name="READ_FILE", params={"filename": "notes.txt"})


def test_parse_read_file_multiple_words() -> None:
    """Le nom de fichier peut contenir plusieurs mots."""
    intent = CommandParser().parse("lecture mon rapport final.txt")
    assert intent == Intent(
        name="READ_FILE", params={"filename": "mon rapport final.txt"}
    )


def test_parse_read_file_without_filename_returns_error() -> None:
    """'lis' sans fichier → erreur avec message demandant le fichier."""
    intent = CommandParser().parse("lis")
    assert intent is not None
    assert intent.name == "ERROR"
    assert "msg" in intent.params


def test_intent_params_default_to_empty_dict() -> None:
    """Intent.params est un dict vide par défaut (pas None)."""
    intent = Intent(name="GREETING")
    assert intent.params == {}
    # Vérifie que chaque Intent a son propre dict (pas partagé)
    other = Intent(name="EXIT")
    assert intent.params is not other.params
