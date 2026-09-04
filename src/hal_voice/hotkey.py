"""
hotkey — Raccourcis clavier globaux via pynput (cross-platform).

Permet d'écouter des raccourcis clavier même quand l'application
n'est pas au premier plan. Fonctionne sur Windows, Linux et macOS.

Utilisation ::
    from hal_voice.hotkey import HotkeyManager
    hm = HotkeyManager()
    hm.register("<f8>", ma_fonction)
    hm.start()

Limitations actuelles :
    - Les combos avec modifiers (Ctrl+Alt+H) ne vérifient que la dernière touche
    - Pour des combos complexes, il faudrait tracker l'état des modifiers
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pynput import keyboard

log = logging.getLogger(__name__)


class HotkeyManager:
    """Écoute des raccourcis clavier globaux et déclenche des callbacks.

    Fonctionnement :
        1. On enregistre des raccourcis via register(combo, callback)
        2. start() lance un listener en arrière-plan (thread daemon)
        3. À chaque frappe, on vérifie si elle correspond à un raccourci
        4. Si oui, on exécute le callback associé
    """

    def __init__(self) -> None:
        # Dictionnaire raccourci → callback
        self._hotkeys: dict[str, Callable[[], None]] = {}
        # Listener pynput (thread daemon qui écoute les frappes)
        self._listener: keyboard.Listener | None = None

    def register(self, combo: str, callback: Callable[[], None]) -> None:
        """Enregistre un raccourci ``combo`` (ex: '<f8>', '<ctrl>+<alt>+h').

        Le format suit la convention pynput :
            - Touches simples : '<f8>', '<space>', '<enter>'
            - Combinaisons : '<ctrl>+<alt>+h'
        """
        self._hotkeys[combo] = callback

    def start(self) -> None:
        """Démarre l'écoute des frappes clavier.

        Le listener tourne en arrière-plan (thread daemon).
        Ne fait rien si aucun raccourci n'est enregistré.
        """
        if not self._hotkeys:
            log.debug("Aucun hotkey enregistré, skip démarrage listener.")
            return

        def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            """Callback appelé à chaque frappe de touche.

            Pour chaque raccourci enregistré, vérifie si la touche
            correspond. Si oui, exécute le callback (protégé par try/except).
            """
            if key is None:
                return
            for combo, callback in self._hotkeys.items():
                if self._match_combo(key, combo):
                    try:
                        callback()
                    except Exception:
                        log.exception("Erreur dans le callback hotkey %s", combo)

        # Listener daemon : le thread s'arrête automatiquement quand le
        # programme principal quitte
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
        """Vérification simplifiée d'un raccourci (1 touche ou combinaison).

        Pour les combos multi-touches (ex: "<ctrl>+<alt>+h"), on vérifie
        uniquement la dernière touche. Pour une vérification complète,
        il faudrait tracker l'état des modifiers (Ctrl, Alt, etc.).
        """
        parts = [p.strip().lower() for p in combo.split("+")]
        if len(parts) == 1:
            return _key_matches(key, parts[0])
        # Pour les combos, on vérifie juste la dernière touche
        # (limitation connue — voir docstring du module)
        return _key_matches(key, parts[-1])


def _key_matches(key: keyboard.Key | keyboard.KeyCode, expected: str) -> bool:
    """Compare une touche pressée à un nom de touche attendu.

    Gère deux types de touches :
        - Touches caractère (key.char) : compare le caractère
        - Touches spéciales (key.name) : compare le nom (ex: "f8", "space")
    """
    if hasattr(key, "char") and key.char:
        return key.char.lower() == expected.lower()
    if hasattr(key, "name"):
        return key.name.lower() == expected.lower()
    return False


__all__ = ["HotkeyManager"]
