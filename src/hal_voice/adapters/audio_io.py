"""
adapters.audio_io — Capture micro + lecture audio (implémentation concrète).

Vérifie les protocoles IAudioCapture et IAudioPlayback.

Cible : Linux/WSL2. L'audio passe par PulseAudio (parecord/paplay).

Architecture :
    - WSL2 → PulseAudio for Windows (build pgaskin) expose le micro
      (module-waveout) et les haut-parleurs (sink waveout) via TCP 4713.
      On capture avec ``parecord`` et on joue avec ``paplay``.

    Pièges connus :
        - ``parecord`` sous WSL n'a PAS d'option ``--duration``
        - Écrire sur ``/dev/stdout`` échoue → on écrit dans un fichier .raw
        - ``module-waveout`` nécessite un ``input_device=<index>`` explicite
        - ``default.pa`` charge souvent ``module-waveout`` sans ``input_device``,
          créant une source ``wavein`` silencieuse
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
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

# ──────────────────────────────────────────────────────────────────────
# Micro par défaut Windows — alternative au test d'amplitude par device
# ──────────────────────────────────────────────────────────────────────
#
# Plutôt que de capturer ~1s sur chaque device pour deviner le bon micro
# (lent, et échoue quand le micro voulu n'est même pas exposé par
# PulseAudio), on interroge directement Windows : l'API Core Audio
# (MMDevice ::GetDefaultAudioEndpoint) donne le micro de capture par défaut
# que l'utilisateur a choisi dans Paramètres > Son > Entrée. On retrouve
# ensuite son index WaveIn (la liste waveInGetDevCaps est celle que
# module-waveout expose) et on sélectionne la source PulseAudio dont la
# description correspond.
#
# NOTE : cette version intégrée reflète scripts/get-default-mic.ps1
# (utilisé par setup.bat pour écrire halvoice.pa). Garder les deux en phase.
_WINDOWS_DEFAULT_MIC_PS = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct HalVoiceWaveCap {
    public ushort wMid;
    public ushort wPid;
    public uint vDriverVersion;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string szPname;
    public uint dwFormats;
    public ushort wChannels;
    public ushort wReserved;
}

public static class HalVoiceWinApi {
    [DllImport("winmm.dll")]
    public static extern uint waveInGetNumDevs();
    [DllImport("winmm.dll")]
    public static extern uint waveInGetDevCaps(
        uint id, ref HalVoiceWaveCap caps, uint size);

    [Guid("D666063F-1587-4E43-81F1-B948E807363F"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceProbe {
        int a();
        int o();
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
    }

    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumeratorProbe {
        int f();
        int GetDefaultAudioEndpoint(
            int dataFlow, int role, out IMMDeviceProbe endpoint);
    }

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    class MmDeviceEnumeratorComObjectProbe { }

    public static string DefaultCaptureId() {
        var enumerator =
            (IMMDeviceEnumeratorProbe)(new MmDeviceEnumeratorComObjectProbe());
        IMMDeviceProbe endpoint;
        Marshal.ThrowExceptionForHR(
            enumerator.GetDefaultAudioEndpoint(1, 1, out endpoint));
        string id;
        Marshal.ThrowExceptionForHR(endpoint.GetId(out id));
        return id;
    }
}
'@

function Get-HalVoiceScore([string]$a, [string]$b) {
    $normA = (($a.ToLowerInvariant()) -replace '[^a-z0-9 ]', ' ')
    $normB = (($b.ToLowerInvariant()) -replace '[^a-z0-9 ]', ' ')
    $tokA = @($normA -split '\s+' | Where-Object { $_ })
    $tokB = @($normB -split '\s+' | Where-Object { $_ })
    if ($tokA.Count -eq 0 -or $tokB.Count -eq 0) { return 0.0 }
    $matches = 0.0
    $total = 0.0
    foreach ($t in $tokA) { $total += $t.Length }
    foreach ($t in $tokB) { $total += $t.Length }
    foreach ($ta in $tokA) {
        foreach ($tb in $tokB) {
            if ($ta -eq $tb) { $matches += $ta.Length * 2.0 }
        }
    }
    if ($total -eq 0) { return 0.0 }
    return $matches / $total
}

try {
    $defaultId = [HalVoiceWinApi]::DefaultCaptureId()
} catch { exit 0 }
$defKey = "HKLM:\SYSTEM\CurrentControlSet\Enum\SWD\MMDEVAPI\$defaultId"
$defaultName =
    (Get-ItemProperty $defKey -ErrorAction SilentlyContinue).FriendlyName
if (-not $defaultName) { exit 0 }

$count = [HalVoiceWinApi]::waveInGetNumDevs()
$capsSize = [System.Runtime.InteropServices.Marshal]::SizeOf(
    [type][HalVoiceWaveCap])
$bestIndex = -1
$bestName = ""
$bestScore = 0.0
for ($i = 0; $i -lt $count; $i++) {
    $caps = New-Object HalVoiceWaveCap
    [void][HalVoiceWinApi]::waveInGetDevCaps(
        [uint32]$i, [ref]$caps, [uint32]$capsSize)
    $score = Get-HalVoiceScore $defaultName $caps.szPname
    if ($score -gt $bestScore) {
        $bestScore = $score
        $bestIndex = $i
        $bestName = $caps.szPname
    }
}
if ($bestIndex -ge 0) {
    Write-Output ("index=" + $bestIndex)
    Write-Output ("name=" + $defaultName)
    Write-Output ("szpname=" + $bestName)
}
"""


def _windows_default_mic(timeout: float = 20.0) -> dict[str, str] | None:
    """Interroge Windows pour le micro de capture par défaut (via PowerShell).

    Depuis WSL2, ``powershell.exe`` est interopérable → on lance le helper
    intégré (équivalent de ``scripts/get-default-mic.ps1``) et on parse ses
    sorties ``clé=valeur`` :
        - ``index``   → index WaveIn (0 = source ``wavein``)
        - ``name``    → nom "friendly" du micro par défaut (MMDevice)
        - ``szpname`` → nom ``waveInGetDevCaps`` qui sert de description
                        ("WaveIn on <szpname>") dans PulseAudio

    Renvoie ``None`` si l'interrogation échoue (pas de Windows / pas de
    micro par défaut trouvé) — dans ce cas on garde le fallback par
    amplitude.
    """
    if shutil.which("powershell.exe") is None:
        return None
    try:
        encoded = base64.b64encode(_WINDOWS_DEFAULT_MIC_PS.encode("utf-16-le")).decode("ascii")
        out = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        log.warning("Impossible d'interroger le micro par défaut Windows", exc_info=True)
        return None

    data: dict[str, str] = {}
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if "=" in line:
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    if "index" not in data or not data["index"].isdigit():
        return None
    log.info("Micro par défaut Windows : index=%s name=%s", data.get("index"), data.get("name"))
    return data


def _pulse_list_sources_detailed(server: str | None = None) -> dict[str, str]:
    """Liste les sources avec leur description ``device.description``.

    ``pactl list sources`` (format complet) renseigne pour chaque source
    ``Name: <name>`` et ``device.description = "<desc>"``. Le module
    module-waveout de PulseAudio Windows pose ``description = "WaveIn on
    <szpname>"`` — c'est ce qui permet de retrouver la source correspondant
    au micro par défaut Windows sans aucun test d'amplitude.
    """
    env = {**os.environ}
    if server:
        env["PULSE_SERVER"] = server
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sources"],
            text=True,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    detailed: dict[str, str] = {}
    name = ""
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith('device.description =') and name:
            detailed[name] = line.split("=", 1)[1].strip().strip('"').strip("'")
    return detailed


def _description_matches_wavein(description: str, device_name: str) -> bool:
    """Vrai si ``description`` (PulseAudio) référence bien ``device_name``.

    Normalise (minuscules, alphanumériques) et vérifie que le nom du device
    apparaît dans la description "WaveIn on <szpname>".
    """

    def _norm(s: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", s.lower()))

    desc, device = _norm(description), _norm(device_name)
    return bool(device) and device in desc


def _test_source_amplitude(source: str, server: str | None = None, duration: float = 1.0) -> int:
    """Teste un device PulseAudio en capturant ``duration`` secondes.

    Renvoie l'amplitude maximale (int). 0 = silence complet.
    """
    n_samples = int(duration * 16_000)
    expected_bytes = n_samples * 2
    fd, tmp_path = tempfile.mkstemp(suffix=".raw")
    os.close(fd)
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
    """Trouve le device d'entrée PulseAudio (pas un monitor).

    Stratégie — par ordre de préférence :
        1. **Micro par défaut Windows** : on interroge Windows (MMDevice)
           pour l'entrée sélectionnée par l'utilisateur, puis on retrouve la
           source PulseAudio dont la description correspond. **Aucun test
           d'amplitude** : c'est le choix de l'utilisateur, pas le device qui
           capte le plus fort.
        2. Fallback historique : test d'amplitude (~1s par source) quand
           l'interrogation Windows n'est pas possible.
    """
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

    # 1. Micro par défaut Windows (interrogation directe, sans test audio)
    windows_mic = _windows_default_mic()
    if windows_mic:
        device_key = windows_mic.get("szpname") or windows_mic.get("name") or ""
        chosen = _pick_by_windows_mic(candidates, server, windows_mic, device_key)
        if chosen is not None:
            return chosen
        log.warning(
            "Micro par défaut Windows (%s, index %s) introuvable dans PulseAudio"
            " — halvoice.pa pointe peut-être sur l'ancien micro. Lance "
            "scripts/setup.bat pour corriger input_device.",
            windows_mic.get("name"),
            windows_mic.get("index"),
        )

    # 2. Fallback : test d'amplitude historique
    chosen, best_amp = _pick_by_amplitude(candidates, server)
    if best_amp > 100:
        return chosen
    log.warning("Aucun device ne capte (>100), utilisation de %s", candidates[0])
    return candidates[0]


def _pick_by_windows_mic(
    candidates: list[str],
    server: str | None,
    windows_mic: dict,
    device_key: str,
) -> str | None:
    """Retourne la source PulseAudio dont la description correspond au micro
    par défaut Windows, ou None si aucune ne correspond."""
    detailed = _pulse_list_sources_detailed(server)
    for src_name in candidates:
        desc = detailed.get(src_name, "")
        if _description_matches_wavein(desc, device_key):
            log.info(
                "Device choisi d'après le micro par défaut Windows : %s (%s)",
                src_name,
                windows_mic.get("name"),
            )
            return src_name
    return None


def _pick_by_amplitude(candidates: list[str], server: str | None) -> tuple[str, int]:
    """Teste l'amplitude de chaque source (~1s) et retourne (meilleure source,
    amplitude max). Plus forte amplitude l'emporte, pas de tie-break."""
    best_source = candidates[0]
    best_amp = 0
    for src_name in candidates:
        amp = _test_source_amplitude(src_name, server, duration=1.0)
        if amp > best_amp:
            best_amp = amp
            best_source = src_name
    return best_source, best_amp


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

    Abstraction au-dessus de PulseAudio (parecord/paplay).
    On est sur Linux/WSL2 : pas de backend noise/sounddevice.
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

        self._use_pulse = True
        self._pulse_server: str | None = None
        self._pulse_input: str | None = None
        self._pulse_output: str | None = None

        if shutil.which("parecord") is None:
            log.error("parecord introuvable — installe pulseaudio-utils")
            return

        self._pulse_server = _pulse_find_server()
        self._pulse_input = _pulse_find_input_device(self._pulse_server)
        self._pulse_output = _pulse_find_output_device(self._pulse_server)
        log.info(
            "Server=%s input=%s output=%s",
            self._pulse_server or "WSLg (défaut)",
            self._pulse_input,
            self._pulse_output,
        )

    def list_devices(self) -> list[dict]:
        """Retourne la liste des sources PulseAudio détectées."""
        return _pulse_list_sources(self._pulse_server)

    def default_input_name(self) -> str:
        """Retourne le nom du device d'entrée sélectionné."""
        return self._pulse_input or ""

    def default_output_name(self) -> str:
        """Retourne le nom du device de sortie sélectionné."""
        return self._pulse_output or ""

    # ── Capture ──────────────────────────────────────────────────────

    def record(self, duration_seconds: float) -> np.ndarray:
        """Capture ``duration_seconds`` du micro et renvoie un numpy array int16 mono."""
        return self._record_pulse(duration_seconds)

    def _record_pulse(self, duration_seconds: float) -> np.ndarray:
        """Capture via parecord (PulseAudio) en PCM brut s16le."""
        n_samples = int(duration_seconds * self.sample_rate * self.channels)
        if not self._pulse_input:
            log.warning("Aucun device PulseAudio trouvé — retour au silence")
            return np.zeros((n_samples, 1), dtype=np.int16)

        fd, tmp_path = tempfile.mkstemp(suffix=".raw")
        os.close(fd)
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
        self._play_pulse(audio, sample_rate)

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
        except (subprocess.CalledProcessError, FileNotFoundError):
            log.exception("Erreur lecture paplay")
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


def _source_marker(name: str) -> str:
    """Renvoie un marqueur descriptif pour une source PulseAudio."""
    lower = name.lower()
    if "monitor" in lower:
        return " [MONITOR - ignore]"
    if any(p in lower for p in _MIC_PATTERNS):
        return " [*** MICRO ***]"
    if "wavein" in lower:
        return " [*** MICRO - Windows ***]"
    if any(p in lower for p in _RDP_PATTERNS):
        return " [RDP fallback - silence]"
    return ""


def pulse_diagnostics() -> None:
    """Affiche les diagnostics PulseAudio complets."""
    if not _is_wsl():
        print("Pas sous WSL2 — skip diagnostics PulseAudio")
        return

    print("=== Diagnostics PulseAudio (WSL2) ===\n")

    windows_mic = _windows_default_mic()
    print("Micro par défaut Windows :")
    if windows_mic:
        print(f"  index={windows_mic.get('index')} name={windows_mic.get('name')}")
        print(f"  szpname={windows_mic.get('szpname')}")
    else:
        print("  inconnu (powershell.exe indisponible ou aucun micro par défaut)")

    print()

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
        marker = _source_marker(str(src["name"]))
        print(f"  index={src['index']} name={src['name']}{marker}")

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
    print("Backend : PulseAudio (parecord/paplay)")
    print(f"PulseAudio server : {io._pulse_server or 'WSLg (défaut)'}")
    print(f"PulseAudio input  : {io._pulse_input}")
    print(f"PulseAudio output : {io._pulse_output}")
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
