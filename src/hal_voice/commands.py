"""Backward-compat : imports déplacés vers hal_voice.domain + hal_voice.use_cases."""

from hal_voice.domain.entities import Intent
from hal_voice.use_cases.command_parser import CommandParser

__all__ = ["CommandParser", "Intent"]
