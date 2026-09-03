"""Tests du parser de commandes vocales (commands.py)."""

from __future__ import annotations

from hal_voice.commands import CommandParser, Intent


def test_parse_empty_returns_none() -> None:
    assert CommandParser().parse("") is None
    assert CommandParser().parse("   ") is None
    assert CommandParser().parse(None) is None  # type: ignore[arg-type]


def test_parse_unknown_text_returns_none() -> None:
    assert CommandParser().parse("bla bla bla") is None


def test_parse_greeting() -> None:
    intent = CommandParser().parse("bonjour")
    assert intent == Intent(name="GREETING")
    assert intent is not None and intent.params == {}


def test_parse_greeting_ignores_case_and_whitespace() -> None:
    intent = CommandParser().parse("  SALUT  ")
    assert intent == Intent(name="GREETING")


def test_parse_stop_synonyms() -> None:
    for text in ("stop", "arrête", "silence"):
        assert CommandParser().parse(text) == Intent(name="STOP")


def test_parse_exit_synonyms() -> None:
    for text in ("au revoir", "quitte", "ferme"):
        assert CommandParser().parse(text) == Intent(name="EXIT")


def test_parse_multiword_trigger_embedded_in_sentence() -> None:
    intent = CommandParser().parse("bonjour, au revoir")
    assert intent == Intent(name="GREETING")


def test_parse_read_file_with_filename() -> None:
    intent = CommandParser().parse("lis notes.txt")
    assert intent == Intent(name="READ_FILE", params={"filename": "notes.txt"})


def test_parse_read_file_multiple_words() -> None:
    intent = CommandParser().parse("lecture mon rapport final.txt")
    assert intent == Intent(
        name="READ_FILE", params={"filename": "mon rapport final.txt"}
    )


def test_parse_read_file_without_filename_returns_error() -> None:
    intent = CommandParser().parse("lis")
    assert intent is not None
    assert intent.name == "ERROR"
    assert "msg" in intent.params


def test_intent_params_default_to_empty_dict() -> None:
    intent = Intent(name="GREETING")
    assert intent.params == {}

    other = Intent(name="EXIT")
    assert intent.params is not other.params
