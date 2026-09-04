"""
adapters.hotkey — Raccourcis clavier globaux via pynput.

Implémentation concrète du monitoring des raccourcis clavier.
Fonctionne sur Linux et WSL2.

Limitations :
    - Les combos avec modifiers ne vérifient que la dernière touche
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pynput import keyboard

log = logging.getLogger(__name__)


class HotkeyManager:
    """Écoute des raccourcis clavier globaux et déclenche des callbacks."""

    def __init__(self) -> None:
        self._hotkeys: dict[str, Callable[[], None]] = {}
        self._listener: keyboard.Listener | None = None

    def register(self, combo: str, callback: Callable[[], None]) -> None:
        """Enregistre un raccourci ``combo`` (ex: '<f8>', '<ctrl>+<alt>+h')."""
        self._hotkeys[combo] = callback

    def start(self) -> None:
        """Démarre l'écoute des frappes clavier (thread daemon)."""
        if not self._hotkeys:
            log.debug("Aucun hotkey enregistré, skip démarrage listener.")
            return

        def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if key is None:
                return
            for combo, callback in self._hotkeys.items():
                if self._match_combo(key, combo):
                    try:
                        callback()
                    except Exception:
                        log.exception("Erreur dans le callback hotkey %s", combo)

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()
        log.info("Hotkey listener démarré (%d raccourci(s)).", len(self._hotkeys))

    def stop(self) -> None:
        """Arrête l'écoute des frappes clavier."""
        if self._listener:
            self._listener.stop()
            self._listener = None

    @staticmethod
    def _match_combo(key: keyboard.Key | keyboard.KeyCode, combo: str) -> bool:
        """Vérification simplifiée d'un raccourci (1 touche ou combinaison)."""
        parts = [p.strip().lower() for p in combo.split("+")]
        if len(parts) == 1:
            return _key_matches(key, parts[0])
        return _key_matches(key, parts[-1])


def _key_matches(key: keyboard.Key | keyboard.KeyCode, expected: str) -> bool:
    """Compare une touche pressée à un nom de touche attendu."""
    if hasattr(key, "char") and key.char:
        return key.char.lower() == expected.lower()
    if hasattr(key, "name"):
        return key.name.lower() == expected.lower()
    return False
