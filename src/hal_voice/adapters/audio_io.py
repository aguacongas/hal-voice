"""
adapters.audio_io — Capture micro + lecture audio (implémentation concrète).

Vérifie les protocoles IAudioCapture et IAudioPlayback.

Cross-platform : sounddevice (PortAudio) par défaut, fallback PulseAudio
(parecord/paplay) sur WSL2.

Architecture :
    - Windows natif  → sounddevice (PortAudio) fonctionne directement.
    - WSL2           → sounddevice ne voit pas le micro Windows. On utilise
      PulseAudio for Windows (build pgaskin) qui expose le micro via TCP 4713.

    Pièges connus :
        - ``parecord`` sous WSL n'a PAS d'option ``--duration``
        - Écrire sur ``/dev/stdout`` échoue → on écrit dans un fichier .raw
        - ``module-waveout`` nécessite un ``input_device=<index>`` explicite
        - ``default.pa`` charge souvent ``module-waveout`` sans ``input_device``,
          créant une source ``wavein`` silencieuse
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from hal_voice.domain.config import DEFAULT_CHANNELS, DEFAULT_DTYPE, DEFAULT_SAMPLE_RATE

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Fonctions utilitaires WSL / PulseAudio
# ══════════════════════════════════════════════════════════════════════


def _is_wsl() -> bool:
    """Détecte si on tourne sous WSL2."""
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _get_windows_host_ip() -> str | None:
    """Récupère l'IP de la machine Windows hôte depuis WSL."""
    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.split()[2]
    except (subprocess.CalledProcessError, IndexError, FileNotFoundError):
        return None


def _pulse_find_server() -> str | None:
    """Trouve le meilleur serveur PulseAudio disponible (TCP Windows ou WSLg)."""
    host_ip = _get_windows_host_ip()
    if host_ip:
        tcp_server = f"tcp:{host_ip}"
        try:
            subprocess.run(
                ["pactl", "info"],
                env={**os.environ, "PULSE_SERVER": tcp_server},
                capture_output=True,
                timeout=3,
                check=True,
            )
            log.info("PulseAudio Windows détecté sur %s", tcp_server)
            return tcp_server
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None


def _pulse_list_sources(server: str | None = None) -> list[dict[str, str | int]]:
    """Liste les sources PulseAudio disponibles."""
    env = {**os.environ}
    if server:
        env["PULSE_SERVER"] = server
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sources", "short"],
            text=True,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    sources = []
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sources.append({"index": int(parts[0]), "name": parts[1]})
    return sources


_MIC_PATTERNS = ["alsa_input", "usb", "mic", "microphone", "webcam", "capture"]
_RDP_PATTERNS = ["rdpsource", "rdp"]


def _test_source_amplitude(
    source: str, server: str | None = None, duration: float = 1.0
) -> int:
    """Teste un device PulseAudio en capturant ``duration`` secondes.

    Renvoie l'amplitude maximale (int). 0 = silence complet.
    """
    n_samples = int(duration * 16_000)
    expected_bytes = n_samples * 2
    tmp_path = tempfile.mktemp(suffix=".raw")
    env = {**os.environ}
    if server:
        env["PULSE_SERVER"] = server
    try:
        proc = subprocess.Popen(
            [
                "parecord",
                f"--device={source}",
                "--format=s16le",
                "--rate=16000",
                "--channels=1",
                tmp_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        return 0
    start = time.monotonic()
    try:
        while True:
            if time.monotonic() - start > duration + 3:
                break
            time.sleep(0.05)
            try:
                if Path(tmp_path).stat().st_size >= expected_bytes:
                    break
            except OSError:
                pass
    except KeyboardInterrupt:
        pass
    proc.terminate()
    try:
        proc.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    try:
        data = np.fromfile(tmp_path, dtype=np.int16, count=n_samples)
    except OSError:
        return 0
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return int(data.max()) if len(data) > 0 else 0


def _pulse_find_input_device(server: str | None = None) -> str | None:
    """Trouve le meilleur device d'entrée PulseAudio (pas un monitor)."""
    candidates: list[str] = []
    rdp_fallback: str | None = None
    for src in _pulse_list_sources(server):
        name = str(src["name"]).lower()
        if "monitor" in name:
            continue
        if any(p in name for p in _RDP_PATTERNS):
            rdp_fallback = str(src["name"])
            continue
        candidates.append(str(src["name"]))

    if not candidates:
        return rdp_fallback

    if len(candidates) == 1:
        return candidates[0]

    log.info("Test de %d devices PulseAudio...", len(candidates))
    best_source = candidates[0]
    best_amp = 0
    for src_name in candidates:
        amp = _test_source_amplitude(src_name, server, duration=1.0)
        log.info("  %s -> amplitude %d", src_name, amp)
        if amp > best_amp:
            best_amp = amp
            best_source = src_name

    if best_amp > 100:
        log.info("Device choisi : %s (amplitude %d)", best_source, best_amp)
        return best_source

    log.warning("Aucun device ne capte (>100), utilisation de %s", candidates[0])
    return candidates[0]


def _pulse_find_output_device(server: str | None = None) -> str | None:
    """Trouve le meilleur device de sortie PulseAudio."""
    env = {**os.environ}
    if server:
        env["PULSE_SERVER"] = server
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sinks", "short"],
            text=True,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            return str(parts[1])
    return None


# ══════════════════════════════════════════════════════════════════════
# Classe AudioIO — API principale
# ══════════════════════════════════════════════════════════════════════


class AudioIO:
    """Helper pour capturer et lire de l'audio en PCM.

    Abstraction au-dessus de sounddevice (PortAudio) et PulseAudio.
    Dispatche automatiquement entre les deux backends.
    """

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
        self._pulse_server: str | None = None
        self._pulse_input: str | None = None
        self._pulse_output: str | None = None

        if self._use_pulse:
            self._pulse_server = _pulse_find_server()
            self._pulse_input = _pulse_find_input_device(self._pulse_server)
            self._pulse_output = _pulse_find_output_device(self._pulse_server)
            log.info(
                "WSL2 — server=%s input=%s output=%s",
                self._pulse_server or "WSLg (défaut)",
                self._pulse_input,
                self._pulse_output,
            )

    def list_devices(self) -> list[dict]:
        """Retourne la liste des devices audio détectés (sounddevice)."""
        return sd.query_devices()  # type: ignore[return-value]

    def default_input_name(self) -> str:
        """Retourne le nom du device d'entrée par défaut."""
        return sd.query_devices(kind="input")["name"]  # type: ignore[index]

    def default_output_name(self) -> str:
        """Retourne le nom du device de sortie par défaut."""
        return sd.query_devices(kind="output")["name"]  # type: ignore[index]

    # ── Capture ──────────────────────────────────────────────────────

    def record(self, duration_seconds: float) -> np.ndarray:
        """Capture ``duration_seconds`` du micro et renvoie un numpy array int16 mono."""
        if self._use_pulse:
            return self._record_pulse(duration_seconds)
        return self._record_sounddevice(duration_seconds)

    def _record_sounddevice(self, duration_seconds: float) -> np.ndarray:
        """Capture via sounddevice (PortAudio) — backend Windows natif.

        Si le device est indisponible (débranché, occupé), retourne un buffer
        de silence au lieu de crasher la boucle.
        """
        frames = int(duration_seconds * self.sample_rate)
        try:
            audio = sd.rec(
                frames,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                device=self.input_device,
            )
            sd.wait()
        except (sd.PortAudioError, OSError, ValueError) as e:
            log.error("Erreur capture sounddevice : %s", e)
            return np.zeros((frames, 1), dtype=np.int16)
        return np.asarray(audio)

    def _record_pulse(self, duration_seconds: float) -> np.ndarray:
        """Capture via parecord (PulseAudio) en PCM brut s16le."""
        n_samples = int(duration_seconds * self.sample_rate * self.channels)
        if not self._pulse_input:
            log.warning("Aucun device PulseAudio trouvé — retour au silence")
            return np.zeros((n_samples, 1), dtype=np.int16)

        tmp_path = tempfile.mktemp(suffix=".raw")
        cmd = [
            "parecord",
            f"--device={self._pulse_input}",
            "--format=s16le",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            tmp_path,
        ]
        log.debug("parecord cmd: %s", " ".join(cmd))
        env = {**os.environ}
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            log.error("parecord introuvable — installe pulseaudio-utils")
            Path(tmp_path).unlink(missing_ok=True)
            return np.zeros((n_samples, 1), dtype=np.int16)

        expected_bytes = n_samples * 2
        timeout = duration_seconds + 5

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
            return np.zeros((n_samples, 1), dtype=np.int16)

        try:
            data = np.fromfile(tmp_path, dtype=np.int16, count=n_samples)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if len(data) < n_samples:
            padded = np.zeros(n_samples, dtype=np.int16)
            padded[: len(data)] = data
            return padded.reshape(-1, 1)
        return data.reshape(-1, 1)

    # ── Lecture ──────────────────────────────────────────────────────

    def play(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Joue un buffer audio. Bloquant jusqu'à la fin de la lecture."""
        if self._use_pulse:
            self._play_pulse(audio, sample_rate)
        else:
            self._play_sounddevice(audio, sample_rate)

    def _play_sounddevice(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Joue via sounddevice (PortAudio). Ignore les erreurs de device."""
        sr = sample_rate or self.sample_rate
        try:
            sd.play(
                audio,
                samplerate=sr,
                device=self.output_device,
                blocking=True,
            )
        except (sd.PortAudioError, OSError, ValueError) as e:
            log.error("Erreur lecture sounddevice : %s", e)

    def _play_pulse(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Écrit un WAV temporaire et joue via ``paplay``."""
        sr = sample_rate or self.sample_rate
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio, sr, format="WAV", subtype="PCM_16")
            tmp_path = tmp.name
        cmd = ["paplay"]
        if self._pulse_output:
            cmd.extend([f"--device={self._pulse_output}"])
        cmd.append(tmp_path)
        env = {**os.environ}
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server
        try:
            subprocess.run(cmd, capture_output=True, check=True, env=env)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.error("Erreur lecture paplay : %s", e)
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


# ══════════════════════════════════════════════════════════════════════
# Diagnostics et tests
# ══════════════════════════════════════════════════════════════════════


def pulse_diagnostics() -> None:
    """Affiche les diagnostics PulseAudio complets."""
    if not _is_wsl():
        print("Pas sous WSL2 — skip diagnostics PulseAudio")
        return

    print("=== Diagnostics PulseAudio (WSL2) ===\n")

    server = _pulse_find_server()
    if server:
        print(f"[OK] PulseAudio Windows détecté : {server}")
    else:
        print("[INFO] PulseAudio Windows non trouvé — utilisation WSLg (défaut)")
        print("  → Le micro WSLg (RDPSource) ne capture que du silence")
        print("  → Installe PulseAudio Windows + configure PULSE_SERVER")

    print()

    env = {**os.environ}
    if server:
        env["PULSE_SERVER"] = server
    try:
        out = subprocess.check_output(
            ["pactl", "info"], text=True, stderr=subprocess.STDOUT, env=env
        )
        print("[OK] pactl info :")
        for line in out.strip().splitlines():
            if any(k in line.lower() for k in ("server name", "server version", "server string")):
                print(f"  {line.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[ERREUR] pactl info impossible : {e}")
        return

    print()

    sources = _pulse_list_sources(server)
    print(f"Sources PulseAudio ({len(sources)}) :")
    for src in sources:
        name = str(src["name"])
        marker = ""
        if "monitor" in name.lower():
            marker = " [MONITOR - ignore]"
        elif any(p in name.lower() for p in _MIC_PATTERNS):
            marker = " [*** MICRO ***]"
        elif "wavein" in name.lower():
            marker = " [*** MICRO - Windows ***]"
        elif any(p in name.lower() for p in _RDP_PATTERNS):
            marker = " [RDP fallback - silence]"
        print(f"  index={src['index']} name={name}{marker}")

    print()

    io = AudioIO()
    print(f"Device sélectionné : {io._pulse_input}")
    print(f"Device output      : {io._pulse_output}")
    print()

    print("Test capture 3s...")
    audio = io.record(3.0)
    max_amp = int(np.abs(audio).max())
    print(f"  shape={audio.shape}, max_amplitude={max_amp}")
    if max_amp < 100:
        print("  → Faible amplitude — vérifie PulseAudio Windows + PULSE_SERVER")
    else:
        print("  → Son capté OK")


def quick_test() -> None:
    """Boucle 5s : record 3s, replay, affiche devices. Pour test manuel."""
    io = AudioIO()
    backend = "PulseAudio (parecord)" if io._use_pulse else "sounddevice (PortAudio)"
    print(f"Backend : {backend}")
    if io._use_pulse:
        print(f"PulseAudio server : {io._pulse_server or 'WSLg (défaut)'}")
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
