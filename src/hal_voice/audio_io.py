"""
audio_io — capture micro + lecture audio.

Cross-platform : sounddevice (PortAudio) par défaut, fallback PulseAudio (parecord/paplay) sur WSL2.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16_000  # 16 kHz, standard pour STT (Vosk, Whisper...)
DEFAULT_CHANNELS = 1           # mono
DEFAULT_DTYPE = "int16"        # 16 bits, attendu par Vosk


def _is_wsl() -> bool:
    """Détecte si on tourne sous WSL2."""
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _pulse_list_sources() -> list[dict[str, str | int]]:
    """Parse `pactl list sources short` → liste de dicts."""
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sources", "short"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    sources = []
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sources.append({"index": int(parts[0]), "name": parts[1]})
    return sources


# Patterns pour identifier les vrais micros (par priorité décroissante)
_MIC_PATTERNS = ["alsa_input", "usb", "mic", "microphone", "webcam", "capture"]
_RDP_PATTERNS = ["rdpsource", "rdp"]


def _pulse_find_input_device() -> str | None:
    """Trouve le meilleur device d'entrée PulseAudio (pas un monitor).

    Priorité : vrais micros (alsa_input, usb, mic...) > tout device non-monitor.
    RDPSource est en dernier recours seulement.
    """
    candidates: list[str] = []
    rdp_fallback: str | None = None
    for src in _pulse_list_sources():
        name = str(src["name"]).lower()
        if "monitor" in name:
            continue
        if any(p in name for p in _RDP_PATTERNS):
            rdp_fallback = str(src["name"])
            continue
        candidates.append(str(src["name"]))

    # Prioriser les vrais micros
    for candidate in candidates:
        if any(p in candidate.lower() for p in _MIC_PATTERNS):
            return candidate

    # Sinon prendre le premier non-monitor non-RDP
    if candidates:
        return candidates[0]

    # Dernier recours : RDP
    return rdp_fallback


def _pulse_find_output_device() -> str | None:
    """Trouve le meilleur device de sortie PulseAudio."""
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sinks", "short"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            return str(parts[1])
    return None


class AudioIO:
    """Helper pour capturer et lire de l'audio en PCM."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        dtype: str = DEFAULT_DTYPE,
        input_device: int | str | None = None,
        output_device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.input_device = input_device
        self.output_device = output_device
        self._use_pulse = _is_wsl() and shutil.which("parecord") is not None
        self._pulse_input: str | None = None
        self._pulse_output: str | None = None
        if self._use_pulse:
            self._pulse_input = _pulse_find_input_device()
            self._pulse_output = _pulse_find_output_device()
            log.info(
                "WSL2 détecté — PulseAudio input=%s output=%s",
                self._pulse_input,
                self._pulse_output,
            )

    def list_devices(self) -> list[dict]:
        """Retourne la liste des devices audio détectés."""
        return sd.query_devices()  # type: ignore[return-value]

    def default_input_name(self) -> str:
        return sd.query_devices(kind="input")["name"]  # type: ignore[index]

    def default_output_name(self) -> str:
        return sd.query_devices(kind="output")["name"]  # type: ignore[index]

    # ── Capture ──────────────────────────────────────────────────────

    def record(self, duration_seconds: float) -> np.ndarray:
        """Capture ``duration_seconds`` du micro et renvoie un numpy array int16 mono."""
        if self._use_pulse:
            return self._record_pulse(duration_seconds)
        return self._record_sounddevice(duration_seconds)

    def _record_sounddevice(self, duration_seconds: float) -> np.ndarray:
        frames = int(duration_seconds * self.sample_rate)
        audio = sd.rec(
            frames,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            device=self.input_device,
        )
        sd.wait()
        return np.asarray(audio)

    def _record_pulse(self, duration_seconds: float) -> np.ndarray:
        """Capture via parecord (PulseAudio) en PCM brut s16le.

        Parecord écrit vers un fichier temporaire réel (un pipe/stream vers
        ``/dev/stdout`` fait échouer ce build avec "Failed to open audio file").
        Le nom en ``.raw`` force l'écriture en PCM brut s16le (sans header WAV).
        """
        n_samples = int(duration_seconds * self.sample_rate * self.channels)
        if not self._pulse_input:
            log.warning("Aucun device PulseAudio trouvé — retour au silence")
            return np.zeros(n_samples, dtype=np.int16)

        tmp = tempfile.NamedTemporaryFile(suffix=".raw", delete=False)
        tmp_path = tmp.name
        tmp.close()

        cmd = [
            "parecord",
            f"--device={self._pulse_input}",
            "--format=s16le",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            tmp_path,
        ]
        log.debug("parecord cmd: %s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            log.error("parecord introuvable — installe pulseaudio-utils")
            Path(tmp_path).unlink(missing_ok=True)
            return np.zeros(n_samples, dtype=np.int16)

        expected_bytes = n_samples * 2
        timeout = duration_seconds + 5  # marge pour démarrage

        # parecord n'a pas d'option --duration sous WSL : on attend qu'il ait
        # écrit assez de données, puis on le termine.
        start = time.monotonic()
        got_size = 0
        try:
            while got_size < expected_bytes:
                if time.monotonic() - start > timeout:
                    log.error("parecord timeout après %.1fs — kill process", timeout)
                    proc.kill()
                    got_size = Path(tmp_path).stat().st_size
                    break
                time.sleep(0.05)
                got_size = Path(tmp_path).stat().st_size
        except FileNotFoundError:
            got_size = 0

        proc.terminate()
        try:
            _, stderr_data = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            stderr_data = b""

        if stderr_data:
            log.warning("parecord stderr: %s", stderr_data.decode(errors="replace").strip())

        if got_size < 2:
            log.warning("parecord: aucune donnée capturée (%d bytes)", got_size)
            Path(tmp_path).unlink(missing_ok=True)
            return np.zeros(n_samples, dtype=np.int16)

        try:
            data = np.fromfile(tmp_path, dtype=np.int16, count=n_samples)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if len(data) < n_samples:
            padded = np.zeros(n_samples, dtype=np.int16)
            padded[: len(data)] = data
            return padded
        return data

    # ── Lecture ──────────────────────────────────────────────────────

    def play(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Joue un buffer audio. Bloquant."""
        if self._use_pulse:
            self._play_pulse(audio, sample_rate)
        else:
            self._play_sounddevice(audio, sample_rate)

    def _play_sounddevice(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        sr = sample_rate or self.sample_rate
        sd.play(
            audio,
            samplerate=sr,
            device=self.output_device,
            blocking=True,
        )

    def _play_pulse(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Écrit un WAV temp et joue via paplay."""
        sr = sample_rate or self.sample_rate
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio, sr, format="WAV", subtype="PCM_16")
            tmp_path = tmp.name
        cmd = ["paplay"]
        if self._pulse_output:
            cmd.extend([f"--device={self._pulse_output}"])
        cmd.append(tmp_path)
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ── Fichiers ────────────────────────────────────────────────────

    def record_to_file(self, path: str | Path, duration_seconds: float) -> Path:
        """Capture et écrit directement dans un fichier WAV."""
        audio = self.record(duration_seconds)
        out = Path(path)
        sf.write(out, audio, self.sample_rate)
        return out

    def play_file(self, path: str | Path) -> None:
        """Lit un fichier WAV (ou tout format supporté par libsndfile)."""
        data, sr = sf.read(str(path))
        if data.ndim > 1 and self.channels == 1:
            data = data.mean(axis=1)
        if data.dtype != self.dtype and self.dtype == "int16":
            data = (data * 32767).astype("int16")
        self.play(np.asarray(data), sample_rate=sr)


def pulse_diagnostics() -> None:
    """Affiche les diagnostics PulseAudio complets."""
    if not _is_wsl():
        print("Pas sous WSL2 — skip diagnostics PulseAudio")
        return

    print("=== Diagnostics PulseAudio (WSL2) ===\n")

    # Test pulseaudio daemon
    try:
        out = subprocess.check_output(
            ["pactl", "info"], text=True, stderr=subprocess.STDOUT
        )
        print("[OK] pactl info :")
        for line in out.strip().splitlines():
            if any(k in line.lower() for k in ("server name", "server version", "pulse server")):
                print(f"  {line.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[ERREUR] pactl info impossible : {e}")
        print("  → PulseAudio server ne tourne pas ?")
        return

    print()

    # Lister toutes les sources
    sources = _pulse_list_sources()
    print(f"Sources PulseAudio ({len(sources)}) :")
    for src in sources:
        name = str(src["name"])
        marker = ""
        if "monitor" in name.lower():
            marker = " [MONITOR - ignore]"
        elif any(p in name.lower() for p in _MIC_PATTERNS):
            marker = " [*** MICRO ***]"
        elif any(p in name.lower() for p in _RDP_PATTERNS):
            marker = " [RDP fallback]"
        print(f"  index={src['index']} name={name}{marker}")

    print()

    # Device sélectionné
    io = AudioIO()
    print(f"Device sélectionné : {io._pulse_input}")
    print(f"Device output      : {io._pulse_output}")
    print()

    # Test capture 1s
    print("Test capture 1s...")
    audio = io.record(1.0)
    max_amp = int(np.abs(audio).max())
    print(f"  shape={audio.shape}, max_amplitude={max_amp}")
    if max_amp < 100:
        print("  → SILENCE capté — micro ne fonctionne pas")
    else:
        print("  → Son capté OK")


def quick_test() -> None:
    """Boucle 5s : record 3s, replay, affiche devices. Pour test manuel."""
    io = AudioIO()
    backend = "PulseAudio (parecord)" if io._use_pulse else "sounddevice (PortAudio)"
    print(f"Backend : {backend}")
    if io._use_pulse:
        print(f"PulseAudio input  : {io._pulse_input}")
        print(f"PulseAudio output : {io._pulse_output}")
    else:
        print(f"Input par défaut  : {io.default_input_name()}")
        print(f"Output par défaut : {io.default_output_name()}")
    print("Capture 3 sec...")
    audio = io.record(3.0)
    max_amp = int(np.abs(audio).max())
    print(f"Capturé : {audio.shape}, max amplitude = {max_amp}")
    if max_amp < 100:
        print("⚠ Aucun son capté — vérifie ton micro")
    else:
        print("Replay...")
        io.play(audio)
    print("Fin.")


if __name__ == "__main__":
    quick_test()
