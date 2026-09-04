"""
Fixtures pytest partagées.

Sur un runner GitHub Action sans serveur X, l'import de ``pynput.keyboard``
échoue à la collection ("failed to acquire X connection"). On injecte alors un
faux module ``pynput`` dans ``sys.modules`` afin que les tests unitaires
puissent importer ``hal_voice.adapters.hotkey`` et mocker le listener.
Sur une machine de dev avec une session graphique, le vrai ``pynput`` est
utilisé tel quel.
"""

from __future__ import annotations

import sys
import types

try:
    from pynput import keyboard  # noqa: F401
except Exception:
    _keyboard = types.ModuleType("pynput.keyboard")
    _keyboard.Listener = object  # remplacé par MagicMock dans les tests
    _keyboard.Key = type("Key", (), {})
    _keyboard.KeyCode = type("KeyCode", (), {})

    _pynput = types.ModuleType("pynput")
    _pynput.keyboard = _keyboard

    sys.modules.setdefault("pynput", _pynput)
    sys.modules.setdefault("pynput.keyboard", _keyboard)
