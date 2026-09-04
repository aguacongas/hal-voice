"""
Tests audio_io — sans dépendance matérielle pour les tests unitaires.

Les tests qui capturent réellement le micro sont marqués ``requires_hardware``
et ne sont joués que sur les machines avec une carte son active.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from hal_voice.adapters.audio_io import AudioIO
from hal_voice.domain.config import DEFAULT_CHANNELS, DEFAULT_DTYPE, DEFAULT_SAMPLE_RATE


def test_default_constants() -> None:
    """Vérifie que les constantes audio sont bien définies."""
    assert DEFAULT_SAMPLE_RATE == 16000
    assert DEFAULT_CHANNELS == 1
    assert DEFAULT_DTYPE == "int16"


def test_instantiation_uses_defaults() -> None:
    """AudioIO() sans argument utilise les constantes par défaut."""
    io = AudioIO()
    assert io.sample_rate == DEFAULT_SAMPLE_RATE
    assert io.channels == DEFAULT_CHANNELS
    assert io.dtype == DEFAULT_DTYPE


def test_instantiation_accepts_overrides() -> None:
    """AudioIO() accepte des paramètres personnalisés."""
    io = AudioIO(sample_rate=48000, channels=2, dtype="float32")
    assert io.sample_rate == 48000
    assert io.channels == 2
    assert io.dtype == "float32"


def test_list_devices_returns_list() -> None:
    """list_devices() retourne la liste des sources PulseAudio."""
    io = AudioIO()
    devices = io.list_devices()
    assert isinstance(devices, list)
    if devices:
        assert "name" in devices[0]
        assert "index" in devices[0]


@pytest.mark.requires_hardware
def test_record_returns_correct_shape() -> None:
    """record() retourne un array int16 de la bonne forme.

    Shape attendue : (n_samples, 1) où n_samples = duration × sample_rate.
    Le 2e dimension (1) est pour le canal mono.
    """
    io = AudioIO()
    audio = io.record(duration_seconds=0.5)
    assert audio.shape == (int(0.5 * DEFAULT_SAMPLE_RATE), 1)
    assert audio.dtype.name == "int16"


# ── Gestion d'erreurs audio (device indisponible) ────────────────────


def test_record_pulse_returns_silence_without_device() -> None:
    """Sans device PulseAudio, record() renvoie un buffer de silence."""
    io = AudioIO()
    io._pulse_input = None
    audio = io.record(duration_seconds=0.25)
    n = int(0.25 * DEFAULT_SAMPLE_RATE)
    assert audio.shape == (n, 1)
    assert (audio == 0).all()


def test_record_pulse_handles_missing_parecord(monkeypatch) -> None:
    """Si parecord est introuvable, record() renvoie du silence."""
    io = AudioIO()
    io._pulse_input = "wavein"
    io._pulse_server = None

    def _raising_popen(*a, **k):
        raise FileNotFoundError("parecord")

    monkeypatch.setattr("hal_voice.adapters.audio_io.subprocess.Popen", _raising_popen)
    audio = io.record(0.25)
    n = int(0.25 * DEFAULT_SAMPLE_RATE)
    assert audio.shape == (n, 1)
    assert (audio == 0).all()


def test_play_pulse_ignores_paplay_error(monkeypatch, tmp_path) -> None:
    """Si paplay échoue, play() ne lève pas d'exception."""
    io = AudioIO()
    io._pulse_output = "waveout"
    io._pulse_server = None

    def _raising_run(*a, **k):
        raise FileNotFoundError("paplay")

    monkeypatch.setattr("hal_voice.adapters.audio_io.subprocess.run", _raising_run)
    data = np.zeros(100, dtype=np.int16)
    io._play_pulse(data, sample_rate=16000)  # ne doit pas lever


# ── Fonctions utilitaires WSL / PulseAudio ────────────────────────────


def test_is_wsl_non_linux(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr("sys.platform", "win32")
    assert m._is_wsl() is False


def test_is_wsl_linux_with_microsoft(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(m.Path, "read_text", lambda self: "microsoft standard WSL2\n")
    assert m._is_wsl() is True


def test_is_wsl_linux_oserror(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr("sys.platform", "linux")

    def _boom(self, *a, **k):
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", _boom)
    assert m._is_wsl() is False


def test_get_windows_host_ip(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m.subprocess, "check_output", lambda *a, **k: "default via 172.20.1.1 dev eth0\n"
    )
    assert m._get_windows_host_ip() == "172.20.1.1"


def test_get_windows_host_ip_errors(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m.subprocess, "check_output", lambda *a, **k: "short\n")
    assert m._get_windows_host_ip() is None

    def _raise(*a, **k):
        raise FileNotFoundError("ip")

    monkeypatch.setattr(m.subprocess, "check_output", _raise)
    assert m._get_windows_host_ip() is None


def test_pulse_find_server_uses_tcp_host(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m, "_get_windows_host_ip", lambda: "172.20.1.1")
    monkeypatch.setattr(m.subprocess, "run", MagicMock())
    assert m._pulse_find_server() == "tcp:172.20.1.1"


def test_pulse_find_server_falls_back_when_unreachable(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m, "_get_windows_host_ip", lambda: "172.20.1.1")

    def _fail(*a, **k):
        raise subprocess.CalledProcessError(1, "pactl")

    monkeypatch.setattr(m.subprocess, "run", _fail)
    assert m._pulse_find_server() is None


def test_pulse_find_server_no_host(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m, "_get_windows_host_ip", lambda: None)
    assert m._pulse_find_server() is None


def test_pulse_list_sources_parses_lines(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m.subprocess,
        "check_output",
        lambda *a, **k: "0\talsa_input.usb-Mic\n1\twavein\n",
    )
    sources = m._pulse_list_sources("tcp:1.2.3.4")
    assert sources == [{"index": 0, "name": "alsa_input.usb-Mic"}, {"index": 1, "name": "wavein"}]


def test_pulse_list_sources_empty_on_error(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    def _raise(*a, **k):
        raise FileNotFoundError("pactl")

    monkeypatch.setattr(m.subprocess, "check_output", _raise)
    assert m._pulse_list_sources("server") == []


def test_source_marker_patterns() -> None:
    import hal_voice.adapters.audio_io as m

    assert "MONITOR" in m._source_marker("alsa_output.pci.monitor")
    assert "MICRO" in m._source_marker("alsa_input.usb-mic")
    assert "MICRO" in m._source_marker("wavein")
    assert "RDP" in m._source_marker("rdpsource")
    assert m._source_marker("autre_source") == ""


def test_pulse_find_input_device_single_candidate(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m, "_pulse_list_sources", lambda s: [{"index": 0, "name": "alsa_input.mic"}]
    )
    assert m._pulse_find_input_device() == "alsa_input.mic"


def test_pulse_find_input_device_skips_monitor_and_uses_rdp_fallback(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m,
        "_pulse_list_sources",
        lambda s: [
            {"index": 0, "name": "alsa_output.monitor"},
            {"index": 1, "name": "rdpsource.0"},
        ],
    )
    assert m._pulse_find_input_device() == "rdpsource.0"


def test_pulse_find_input_device_picks_best_amplitude(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m,
        "_pulse_list_sources",
        lambda s: [{"index": 0, "name": "src_a"}, {"index": 1, "name": "src_b"}],
    )
    monkeypatch.setattr(
        m, "_test_source_amplitude", lambda src, srv, duration: 500 if src == "src_b" else 50
    )
    assert m._pulse_find_input_device() == "src_b"


def test_pulse_find_input_device_fallback_first_when_low_amp(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m,
        "_pulse_list_sources",
        lambda s: [{"index": 0, "name": "src_a"}, {"index": 1, "name": "src_b"}],
    )
    monkeypatch.setattr(m, "_test_source_amplitude", lambda src, srv, duration: 10)
    assert m._pulse_find_input_device() == "src_a"


def test_pulse_find_output_device_returns_first(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(
        m.subprocess, "check_output", lambda *a, **k: "0\talsa_output.pci.waveout\n1\tredir\n"
    )
    assert m._pulse_find_output_device() == "alsa_output.pci.waveout"


def test_pulse_find_output_device_empty_on_error(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    def _raise(*a, **k):
        raise subprocess.CalledProcessError(1, "pactl")

    monkeypatch.setattr(m.subprocess, "check_output", _raise)
    assert m._pulse_find_output_device() is None


def test_pulse_find_output_device_none_without_parts(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m.subprocess, "check_output", lambda *a, **k: "\n")
    assert m._pulse_find_output_device() is None


def test_test_source_amplitude_returns_max(monkeypatch, tmp_path) -> None:
    import hal_voice.adapters.audio_io as m

    fd, raw = tempfile.mkstemp(suffix=".raw")
    os.close(fd)
    Path(raw).write_bytes(b"\x5c\x03" * 200 + b"\x00\x00" * 200)  # max ~860 en tête

    proc = MagicMock()
    monkeypatch.setattr(m.tempfile, "mkstemp", lambda *a, **k: (fd, raw))
    monkeypatch.setattr(m.os, "close", lambda *a, **k: None)
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(m.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    # La boucle lit la taille reelle du fichier (400 octets) >= expected_bytes
    assert m._test_source_amplitude("src", duration=0.01) > 0
    proc.terminate.assert_called_once()


def test_test_source_amplitude_missing_parecord(monkeypatch, tmp_path) -> None:
    import hal_voice.adapters.audio_io as m

    def _raise(*a, **k):
        raise FileNotFoundError("parecord")

    monkeypatch.setattr(m.subprocess, "Popen", _raise)
    assert m._test_source_amplitude("src") == 0


# ── AudioIO : chemins heureux et API ──────────────────────────────────


def test_default_names_return_empty_without_devices() -> None:
    io = AudioIO()
    io._pulse_input = None
    io._pulse_output = None
    assert io.default_input_name() == ""
    assert io.default_output_name() == ""


def test_list_devices_delegates(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    fake = [{"index": 0, "name": "wavein"}]
    monkeypatch.setattr(m, "_pulse_list_sources", lambda s: fake)
    io = AudioIO()
    monkeypatch.setattr(io, "_pulse_server", None)
    assert io.list_devices() == fake


def test_record_pulse_happy_path(monkeypatch, tmp_path) -> None:
    """_record_pulse capture des données et renvoie un array reshape (-1, 1)."""
    io = AudioIO()
    io._pulse_input = "wavein"
    io._pulse_server = None
    io.sample_rate = 16000
    io.channels = 1

    fd, raw = tempfile.mkstemp(suffix=".raw")
    os.close(fd)
    Path(raw).write_bytes(b"\x01\x00" * 16000)  # 16000 échantillons int16

    proc = MagicMock()
    proc.communicate.return_value = (b"", b"")
    proc.stderr = b""

    state = {"size": 0}

    def _stat_side(self):
        state["size"] = 32000  # le fichier grossit au 2e appel
        return SimpleNamespace(st_size=state["size"])

    monkeypatch.setattr("tempfile.mkstemp", lambda *a, **k: (fd, raw))
    monkeypatch.setattr("hal_voice.adapters.audio_io.os.close", lambda fd: None)
    monkeypatch.setattr("hal_voice.adapters.audio_io.subprocess.Popen", lambda *a, **k: proc)
    monkeypatch.setattr(Path, "stat", _stat_side)
    monkeypatch.setattr("hal_voice.adapters.audio_io.time.monotonic", lambda: 0.0)
    monkeypatch.setattr("hal_voice.adapters.audio_io.time.sleep", lambda s: None)

    audio = io._record_pulse(1.0)
    assert audio.shape[1] == 1
    assert (audio != 0).any()


def test_record_pulse_returns_silence_no_device(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    io = AudioIO()
    io._pulse_input = None
    with monkeypatch.context() as mc:
        mc.setattr(m.log, "warning", lambda *a, **k: None)
        audio = io._record_pulse(0.5)
    n = int(0.5 * 16000)
    assert audio.shape == (n, 1)
    assert (audio == 0).all()


def test_play_pulse_happy_path(monkeypatch) -> None:
    """_play_pulse écrit un WAV et le joue via paplay."""
    io = AudioIO()
    io._pulse_output = "waveout"
    io._pulse_server = None
    io.sample_rate = 16000

    class _FakeNamedTemp:
        def __init__(self, **k):
            self.name = "fake_pulse.wav"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("hal_voice.adapters.audio_io.tempfile.NamedTemporaryFile", _FakeNamedTemp)
    monkeypatch.setattr("hal_voice.adapters.audio_io.sf.write", lambda *a, **k: None)
    monkeypatch.setattr("hal_voice.adapters.audio_io.subprocess.run", MagicMock())

    io._play_pulse(np.zeros(100, dtype=np.int16), sample_rate=16000)


def test_record_to_file_writes_wav(tmp_path, monkeypatch) -> None:
    io = AudioIO()
    monkeypatch.setattr(io, "record", lambda duration: np.zeros((16000, 1), dtype=np.int16))
    monkeypatch.setattr("hal_voice.adapters.audio_io.sf.write", lambda *a, **k: None)
    out = io.record_to_file(tmp_path / "out.wav", 1.0)
    assert out == tmp_path / "out.wav"


def test_play_file_single_channel(monkeypatch) -> None:
    io = AudioIO()
    data = np.zeros(100, dtype=np.float64)
    monkeypatch.setattr("hal_voice.adapters.audio_io.sf.read", lambda p: (data, 16000))
    played = []
    monkeypatch.setattr(io, "play", lambda a, sample_rate: played.append((a, sample_rate)))
    io.play_file("file.wav")
    assert played


def test_play_file_stereo_mixes_and_converts(monkeypatch) -> None:
    io = AudioIO()
    io.channels = 1
    io.dtype = "int16"
    stereo = np.zeros((100, 2), dtype=np.float64)
    monkeypatch.setattr("hal_voice.adapters.audio_io.sf.read", lambda p: (stereo, 16000))
    played = []
    monkeypatch.setattr(io, "play", lambda a, sample_rate: played.append((a, sample_rate)))
    io.play_file("file.wav")
    assert played


# ── pulse_diagnostics ─────────────────────────────────────────────────


def test_pulse_diagnostics_skips_non_wsl(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m, "_is_wsl", lambda: False)
    with patch("builtins.print") as p:
        m.pulse_diagnostics()
    p.assert_any_call("Pas sous WSL2 — skip diagnostics PulseAudio")


def test_pulse_diagnostics_full_flow(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m, "_is_wsl", lambda: True)
    monkeypatch.setattr(m, "_pulse_find_server", lambda: "tcp:1.2.3.4")
    monkeypatch.setattr(
        m.subprocess, "check_output", lambda *a, **k: "Server Name: x\nServer Version: y\n"
    )
    monkeypatch.setattr(
        m,
        "_pulse_list_sources",
        lambda s: [{"index": 0, "name": "wavein"}, {"index": 1, "name": "rdpsource"}],
    )
    io_mock = MagicMock()
    io_mock._pulse_input = "wavein"
    io_mock._pulse_output = "waveout"
    io_mock.record.return_value = np.zeros((48000, 1), dtype=np.int16)
    monkeypatch.setattr(m, "AudioIO", lambda: io_mock)

    with patch("builtins.print") as p:
        m.pulse_diagnostics()
    p.assert_any_call("=== Diagnostics PulseAudio (WSL2) ===\n")


def test_pulse_diagnostics_pactl_error(monkeypatch) -> None:
    import hal_voice.adapters.audio_io as m

    monkeypatch.setattr(m, "_is_wsl", lambda: True)
    monkeypatch.setattr(m, "_pulse_find_server", lambda: None)

    def _raise(*a, **k):
        raise subprocess.CalledProcessError(1, "pactl")

    monkeypatch.setattr(m.subprocess, "check_output", _raise)
    with patch("builtins.print") as p:
        m.pulse_diagnostics()
    p.assert_any_call(
        "[ERREUR] pactl info impossible : Command 'pactl' returned non-zero exit status 1."
    )
