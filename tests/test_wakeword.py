"""
Tests du wake word (détection "+ VAD adaptatif + mode veille").

Use cases purs — aucune dépendance matérielle.
    - WakeWordDetector : correspondance mot d'activation dans un texte
    - AdaptiveVoiceActivity : plancher de bruit + seuil de parole
"""

from __future__ import annotations

import pytest

from hal_voice.use_cases.wakeword import AdaptiveVoiceActivity, WakeWordDetector

# ── WakeWordDetector ─────────────────────────────────────────────────


def test_matches_simple() -> None:
    """Le mot d'activation simple est reconnu."""
    d = WakeWordDetector("hal")
    assert d.matches("salut hal")
    assert d.matches("hal ecoute moi")
    assert d.matches("OK HAL")


def test_matches_case_insensitive() -> None:
    """La détection est insensible à la casse."""
    d = WakeWordDetector("hal")
    assert d.matches("HAL")
    assert d.matches("Hal")


def test_matches_ignores_punctuation() -> None:
    """La ponctuation autour du mot n'empêche pas la détection."""
    d = WakeWordDetector("hal")
    assert d.matches("hal, ecoute")
    assert d.matches("salut hal.")


def test_no_match_when_absent() -> None:
    """Aucun mot d'activation → False."""
    d = WakeWordDetector("hal")
    assert not d.matches("bonjour")
    assert not d.matches("")
    assert not d.matches("   ")


def test_no_false_positive_similar_word() -> None:
    """Un mot ressemblant ('hall', 'halle') ne déclenche pas le wake word."""
    d = WakeWordDetector("hal")
    assert not d.matches("je suis dans le hall")
    assert not d.matches("halle")


def test_matches_multi_word_phrase() -> None:
    """Un wake word multi-mots ('ok hal') exige tous les tokens (ordre libre)."""
    d = WakeWordDetector("ok hal")
    assert d.matches("ok hal lance la musique")
    assert d.matches("hal ok")  # ordre libre mais tokens présents
    assert not d.matches("ok merci")
    assert not d.matches("hal")


def test_strip_removes_wake_word() -> None:
    """strip_wake_word() retire le wake word et garde le reste de la phrase."""
    d = WakeWordDetector("hal")
    assert d.strip_wake_word("hal ecoute ceci") == "ecoute ceci"
    assert d.strip_wake_word("ecoute hal ceci") == "ecoute ceci"
    assert d.strip_wake_word("") == ""


def test_default_wake_word_is_hal() -> None:
    """Le wake word par défaut est 'hal'."""
    assert WakeWordDetector().wake_word == "hal"


# ── AdaptiveVoiceActivity ────────────────────────────────────────────


def test_initial_silence_adapts_floor_down() -> None:
    """En silence constant, le plancher de bruit descend vers l'amplitude."""
    vad = AdaptiveVoiceActivity(init_floor=1000.0, alpha=0.1)
    floor0 = vad.noise_floor
    for _ in range(5):
        assert vad.update(100.0) is False
    assert vad.noise_floor < floor0


def test_loud_amplitude_triggers_speech() -> None:
    """Une amplitude bien au-dessus du plancher signale de la parole."""
    vad = AdaptiveVoiceActivity(init_floor=200.0, factor=3.0)
    assert vad.update(2000.0) is True


def test_threshold_computed_from_floor() -> None:
    """Le seuil de parole vaut plancher × facteur."""
    vad = AdaptiveVoiceActivity(init_floor=500.0, factor=4.0)
    assert vad.threshold == pytest.approx(2000.0)
    assert vad.noise_floor == pytest.approx(500.0)


def test_silence_never_triggers_speech() -> None:
    """Tant que l'amplitude reste sous le seuil, jamais de parole."""
    vad = AdaptiveVoiceActivity(init_floor=1000.0, factor=10.0)
    for _ in range(50):
        assert vad.update(50.0) is False
