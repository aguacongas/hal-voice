"""
Tests end-to-end de l'Orchestrator (Clean Architecture).

Ces tests simulent la boucle complète capture → STT → parsing → TTS
avec des adapters factices (fake implémentant les protocoles du domaine).
Pas de dépendance matérielle ni de vrai micro/TTS.

Ils valident :
    - le flux complet d'une commande (GREETING, STOP, READ_FILE, EXIT)
    - le comportement quand le STT ne détecte rien
    - le comportement quand une erreur survient dans la boucle
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from hal_voice.domain.entities import Intent
from hal_voice.domain.protocols import ISTT, ITTS, IAudioCapture
from hal_voice.use_cases.command_parser import CommandParser
from hal_voice.use_cases.orchestrator import Orchestrator

# ── Fakes (implémentations des protocoles) ───────────────────────────


class FakeCapture(IAudioCapture):
    """Capture factice : renvoie un buffer d'échantillons prédéfini."""

    def __init__(self, samples: list[str]) -> None:
        self._samples = iter(samples)
        self.records = 0

    def record(self, duration_seconds: float) -> np.ndarray:
        self.records += 1
        n = int(duration_seconds * 16000)
        return np.zeros((n, 1), dtype=np.int16)


class FakeSTT(ISTT):
    """STT factice : renvoie la transcription prédéfinie suivante."""

    def __init__(self, transcriptions: list[str | None]) -> None:
        self._transcriptions = list(transcriptions)
        self.calls = 0

    def transcribe_array(
        self, audio: np.ndarray, sample_rate: int | None = None
    ) -> str:
        self.calls += 1
        if not self._transcriptions:
            return ""
        return self._transcriptions.pop(0) or ""


class FakeTTS(ITTS):
    """TTS factice : enregistre les textes prononcés."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped = False

    def speak(self, text: str, blocking: bool = True) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped = True


def _make_orchestrator(
    transcriptions: list[str | None] | None = None,
    samples: list[str] | None = None,
) -> tuple[Orchestrator, FakeCapture, FakeSTT, FakeTTS]:
    """Construit un Orchestrator câblé avec les fakes."""
    capture = FakeCapture(samples or ["x"])
    stt = FakeSTT(transcriptions or [])
    tts = FakeTTS()
    orchestrator = Orchestrator(
        capture=capture, stt=stt, tts=tts, parser=CommandParser()
    )
    return orchestrator, capture, stt, tts


# ── Tests d'exécution d'intentions ───────────────────────────────────


def test_execute_greeting_speaks() -> None:
    """GREETING → le TTS prononce le message de salutation."""
    orch, _, _, tts = _make_orchestrator()
    result = orch.execute_intent(Intent(name="GREETING"))
    assert result is False
    assert "Bonjour" in tts.spoken[-1]


def test_execute_stop_stops_and_speaks() -> None:
    """STOP → coupe la parole puis annonce le silence."""
    orch, _, _, tts = _make_orchestrator()
    result = orch.execute_intent(Intent(name="STOP"))
    assert result is False
    assert tts.stopped is True
    assert "Silence" in tts.spoken[-1]


def test_execute_read_file_missing() -> None:
    """READ_FILE sur un fichier inexistant → message d'erreur."""
    orch, _, _, tts = _make_orchestrator()
    result = orch.execute_intent(
        Intent(name="READ_FILE", params={"filename": "introuvable.txt"})
    )
    assert result is False
    assert "ne trouve pas le fichier" in tts.spoken[-1]


def test_execute_exit_returns_true() -> None:
    """EXIT → dit au revoir et retourne True (quitte la boucle)."""
    orch, _, _, tts = _make_orchestrator()
    result = orch.execute_intent(Intent(name="EXIT"))
    assert result is True
    assert "Au revoir" in tts.spoken[-1]


def test_execute_error_speaks_message() -> None:
    """ERROR → prononce le message d'erreur fourni."""
    orch, _, _, tts = _make_orchestrator()
    result = orch.execute_intent(
        Intent(name="ERROR", params={"msg": "fichier illisible"})
    )
    assert result is False
    assert "fichier illisible" in tts.spoken[-1]


# ── Tests de la boucle run() ─────────────────────────────────────────


def test_run_reads_file_end_to_end(monkeypatch, tmp_path) -> None:
    """Boucle complète : on demande de lire un fichier, on le lit, puis on quitte."""

    doc = tmp_path / "notes.txt"
    doc.write_text("contenu secret", encoding="utf-8")

    capture = FakeCapture(["x"] * 10)
    stt = FakeSTT(
        [
            f"lis {doc}",
            "au revoir",
        ]
    )
    tts = FakeTTS()
    orch = Orchestrator(capture=capture, stt=stt, tts=tts, parser=CommandParser())
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)

    result = orch.run()
    assert result == 0
    assert any("contenu secret" in s for s in tts.spoken)


def test_run_ignores_silence_and_greets(monkeypatch) -> None:
    """La boucle ignore le silence (STT vide) et traite les commandes."""

    capture = FakeCapture(["x"] * 10)
    stt = FakeSTT(
        [
            None,  # silence → ignoré
            "bonjour",
            "au revoir",
        ]
    )
    tts = FakeTTS()
    orch = Orchestrator(capture=capture, stt=stt, tts=tts, parser=CommandParser())
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)

    result = orch.run()
    assert result == 0
    assert any("Bonjour" in s for s in tts.spoken)
    assert any("Au revoir" in s for s in tts.spoken)


def test_run_keyboard_interrupt_returns_zero(monkeypatch) -> None:
    """Ctrl-C (KeyboardInterrupt) → la boucle s'arrête proprement (return 0)."""

    def _raise(*a, **k):
        raise KeyboardInterrupt

    capture = FakeCapture(["x"] * 10)
    stt = FakeSTT([])
    tts = FakeTTS()
    orch = Orchestrator(capture=capture, stt=stt, tts=tts, parser=CommandParser())

    monkeypatch.setattr(
        orch._capture, "record", lambda *a, **k: _raise()
    )

    result = orch.run()
    assert result == 0


# ── Tests de protocole (les fakes respectent bien les contrats) ──────


def test_fakes_implement_protocols() -> None:
    """Les fakes sont bien reconnus comme implémentations des protocoles."""
    assert isinstance(FakeCapture("x"), IAudioCapture)
    assert isinstance(FakeSTT([]), ISTT)
    assert isinstance(FakeTTS(), ITTS)


def test_mock_adapters_work_with_orchestrator() -> None:
    """Les MagicMock implémentent aussi les protocoles (duck typing)."""
    mock_capture = MagicMock()
    mock_capture.record.return_value = np.zeros((48000, 1), dtype=np.int16)
    mock_stt = MagicMock()
    mock_stt.transcribe_array.return_value = "au revoir"
    mock_tts = MagicMock()
    orch = Orchestrator(
        capture=mock_capture, stt=mock_stt, tts=mock_tts, parser=CommandParser()
    )
    assert orch.execute_intent(Intent(name="EXIT")) is True
    mock_tts.speak.assert_called()


def test_unknown_intent_is_noop() -> None:
    """Une intention inconnue ne fait rien et ne quitte pas la boucle."""
    orch, _, _, tts = _make_orchestrator()
    result = orch.execute_intent(Intent(name="FAKE_INTENT"))
    assert result is False
    assert tts.spoken == []


# ── Mode silencieux (--silent) ────────────────────────────────────────


def test_silent_mode_skips_greeting_speech() -> None:
    """En mode silencieux, le TTS ne prononce pas les réponses."""
    tts = FakeTTS()
    orch = Orchestrator(
        capture=FakeCapture(["x"]),
        stt=FakeSTT([]),
        tts=tts,
        parser=CommandParser(),
        silent=True,
    )
    assert orch.execute_intent(Intent(name="GREETING")) is False
    assert tts.spoken == []


def test_silent_mode_still_handles_intents() -> None:
    """Le mode silencieux n'empêche pas l'exécution des intentions."""
    tts = FakeTTS()
    orch = Orchestrator(
        capture=FakeCapture(["x"]),
        stt=FakeSTT([]),
        tts=tts,
        parser=CommandParser(),
        silent=True,
    )
    # EXIT doit toujours quitter la boucle (retourne True)
    assert orch.execute_intent(Intent(name="EXIT")) is True
    # STOP doit toujours appeler tts.stop() mais pas parler
    orch.execute_intent(Intent(name="STOP"))
    assert tts.stopped is True
    assert tts.spoken == []


# ── Config (mode silencieux) ──────────────────────────────────────────


def test_config_silent_from_env(monkeypatch) -> None:
    """HAL_VOICE_SILENT=true active le mode silencieux via la config."""
    monkeypatch.setenv("HAL_VOICE_SILENT", "true")
    monkeypatch.setattr(
        "hal_voice.adapters.config_loader.sys.argv", ["hal_voice"]
    )
    from hal_voice.adapters.config_loader import load_config_from_env

    cfg = load_config_from_env()
    assert cfg.silent is True


def test_config_silent_disable_by_default(monkeypatch) -> None:
    """Sans variable ni argument, silent est False."""
    monkeypatch.delenv("HAL_VOICE_SILENT", raising=False)
    monkeypatch.setattr(
        "hal_voice.adapters.config_loader.sys.argv", ["hal_voice"]
    )
    from hal_voice.adapters.config_loader import load_config_from_env

    cfg = load_config_from_env()
    assert cfg.silent is False


def test_config_silent_from_cli_arg(monkeypatch) -> None:
    """L'argument CLI --silent active le mode silencieux."""
    monkeypatch.delenv("HAL_VOICE_SILENT", raising=False)
    monkeypatch.setattr(
        "hal_voice.adapters.config_loader.sys.argv", ["hal_voice", "--silent"]
    )
    from hal_voice.adapters.config_loader import load_config_from_env

    cfg = load_config_from_env()
    assert cfg.silent is True
