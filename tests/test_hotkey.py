"""
Tests HotkeyManager (pynput) — sans écoute réelle du clavier.

Le listener de pynput est mocké pour éviter de capturer de vraies
frappes pendant les tests unitaires.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from hal_voice.adapters.hotkey import HotkeyManager, _key_matches


def _char_key(char: str) -> SimpleNamespace:
    """Une touche 'texte' (keyboard.KeyCode) factice."""
    return SimpleNamespace(char=char)


def _name_key(name: str) -> SimpleNamespace:
    """Une touche 'spéciale' (keyboard.Key) factice."""
    return SimpleNamespace(name=name)


def _empty_key() -> SimpleNamespace:
    """Une touche sans char ni name."""
    return SimpleNamespace()


# ── _key_matches (comparaison d'une touche à un nom) ──────────────────


def test_key_matches_char() -> None:
    """Une touche avec .char correspond (insensible à la casse)."""
    assert _key_matches(_char_key("F8"), "f8")
    assert _key_matches(_char_key("h"), "H")
    assert not _key_matches(_char_key("h"), "j")


def test_key_matches_name() -> None:
    """Une touche spéciale (keyboard.Key.f8 = .name='f8') correspond."""
    assert _key_matches(_name_key("f8"), "f8")
    assert not _key_matches(_name_key("f9"), "f8")


def test_key_matches_no_char_or_name() -> None:
    """Une touche sans .char ni .name ne correspond jamais."""
    assert not _key_matches(_empty_key(), "f8")


# ── _match_combo (combinaison de touches) ─────────────────────────────


def test_match_combo_single_key_uses_char() -> None:
    manager = HotkeyManager()
    assert manager._match_combo(_char_key("h"), "h")
    assert not manager._match_combo(_char_key("g"), "h")


def test_match_combo_modifier_checks_last_part() -> None:
    """Un combo avec modifiers ne vérifie que la dernière touche."""
    manager = HotkeyManager()
    assert manager._match_combo(_name_key("f8"), "<ctrl>+f8")
    assert not manager._match_combo(_name_key("f9"), "<ctrl>+f8")


# ── register ──────────────────────────────────────────────────────────


def test_register_adds_hotkey() -> None:
    manager = HotkeyManager()
    callback = lambda: None  # noqa: E731
    manager.register("<f8>", callback)
    assert manager._hotkeys["<f8>"] is callback


# ── start / stop (listener mocké) ─────────────────────────────────────


def _mock_listener():
    listener_cls = MagicMock()
    listener_instance = MagicMock()
    listener_cls.return_value = listener_instance
    return listener_cls, listener_instance


def test_start_skips_when_no_hotkeys() -> None:
    """start() sans hotkey enregistré ne crée pas de listener."""
    manager = HotkeyManager()
    with patch("hal_voice.adapters.hotkey.keyboard.Listener") as listener_cls:
        manager.start()
    listener_cls.assert_not_called()
    assert manager._listener is None


def test_start_creates_daemon_listener() -> None:
    """start() avec hotkeys crée un listener daemon et le lance."""
    listener_cls, listener_instance = _mock_listener()
    manager = HotkeyManager()
    manager.register("<f8>", lambda: None)
    with patch("hal_voice.adapters.hotkey.keyboard.Listener", listener_cls):
        manager.start()
    listener_cls.assert_called_once()
    assert listener_instance.daemon is True
    listener_instance.start.assert_called_once()
    assert manager._listener is listener_instance


def test_stop_stops_listener() -> None:
    """stop() arrête le listener et le libère."""
    _, listener_instance = _mock_listener()
    manager = HotkeyManager()
    manager._listener = listener_instance
    manager.stop()
    listener_instance.stop.assert_called_once()
    assert manager._listener is None


def test_stop_without_listener_is_noop() -> None:
    """stop() sans listener ne fait rien."""
    HotkeyManager().stop()


def test_on_press_dispatches_callback() -> None:
    """Quand la touche correspond, le callback est appelé ; sinon non."""
    listener_cls, _ = _mock_listener()
    calls: list[str] = []
    manager = HotkeyManager()
    manager.register("h", lambda: calls.append("h"))
    with patch("hal_voice.adapters.hotkey.keyboard.Listener", listener_cls):
        manager.start()
    on_press = listener_cls.call_args.kwargs["on_press"]
    on_press(_char_key("h"))  # correspond
    assert calls == ["h"]
    on_press(_char_key("x"))  # ne correspond pas
    assert calls == ["h"]


def test_on_press_ignores_none_key() -> None:
    """Une frappe None (touche inconnue) est ignorée."""
    listener_cls, _ = _mock_listener()
    manager = HotkeyManager()
    manager.register("h", lambda: None)
    with patch("hal_voice.adapters.hotkey.keyboard.Listener", listener_cls):
        manager.start()
    on_press = listener_cls.call_args.kwargs["on_press"]
    on_press(None)  # ne doit pas lever


def test_on_press_catches_callback_error(monkeypatch) -> None:
    """Si un callback lève, l'erreur est loggée et pas propagée."""
    listener_cls, _ = _mock_listener()

    def _callback() -> None:
        raise RuntimeError("boom")

    manager = HotkeyManager()
    errors = []

    class _LogException:
        def exception(self, *a, **k):
            errors.append(a)

    monkeypatch.setattr("hal_voice.adapters.hotkey.log.exception", _LogException().exception)
    manager.register("h", _callback)
    with patch("hal_voice.adapters.hotkey.keyboard.Listener", listener_cls):
        manager.start()
    on_press = listener_cls.call_args.kwargs["on_press"]
    on_press(_char_key("h"))  # ne doit pas lever
    assert errors
