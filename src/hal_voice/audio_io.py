"""
audio_io — capture micro + lecture audio.

Cross-platform : sounddevice (PortAudio) par défaut, fallback PulseAudio (parecord/paplay) sur WSL2.

Architecture :
    - Windows natif  → sounddevice (PortAudio) fonctionne directement.
    - WSL2           → sounddevice ne voit pas le micro Windows. On utilise
      PulseAudio for Windows (build pgaskin) qui expose le micro via TCP 4713.
      Le serveur PulseAudio tourne sur Windows et WSL s'y connecte via
      ``parecord``/``paplay``. La détection WSL se fait via ``/proc/version``.

    Priorité PulseAudio :
        1. PulseAudio Windows (TCP 4713) — vrai micro via ``module-waveout``
        2. WSLg (unix socket) — micro virtuel RDP, ne capte que du silence

    Pièges connus :
        - ``parecord`` sous WSL n'a PAS d'option ``--duration`` → on lit un
          nombre fixe de bytes puis on ``terminate()`` le process.
        - Écrire sur ``/dev/stdout`` échoue avec ce build → on écrit dans un
          fichier temporaire réel (suffixe ``.raw`` → PCM brut s16le sans header).
        - ``module-waveout`` nécessite un ``input_device=<index>`` explicite.
          L'index correspond aux indices WaveIn (API Windows) et varie par machine.
        - ``default.pa`` charge souvent ``module-waveout`` sans ``input_device``,
          créant une source ``wavein`` silencieuse. Il faut commenter cette ligne
          pour ne garder que celle de ``halvoice.pa``.
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

log = logging.getLogger(__name__)

# ── Constantes audio ──────────────────────────────────────────────────
# 16 kHz : fréquence d'échantillonnage standard pour la reconnaissance
# vocale (Vosk, Whisper, etc.)
DEFAULT_SAMPLE_RATE = 16_000
# Mono : un seul canal, suffisant pour la STT
DEFAULT_CHANNELS = 1
# int16 : 16 bits signés, format natif attendu par Vosk
DEFAULT_DTYPE = "int16"


# ══════════════════════════════════════════════════════════════════════
# Fonctions utilitaires WSL / PulseAudio
# ══════════════════════════════════════════════════════════════════════


def _is_wsl() -> bool:
    """Détecte si on tourne sous WSL2.

    WSL2 identifie le noyau Linux avec la chaîne "microsoft" dans
    ``/proc/version`` (ex: "Linux version 5.15... (microsoft@...").
    WSL1 utilise un noyau différent sans ce marqueur.
    """
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _get_windows_host_ip() -> str | None:
    """Récupère l'IP de la machine Windows hôte depuis WSL.

    La passerelle par défaut de WSL pointe vers Windows :
    ``ip route show default`` → "default via 172.17.192.1 dev eth0 ..."
    On extrait le 3ème champ (= l'IP Windows).
    Retourne None si la commande échoue.
    """
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
    """Trouve le meilleur serveur PulseAudio disponible.

    Priorité : PulseAudio Windows (TCP 4713) > WSLg (unix socket).
    PulseAudio Windows expose le vrai micro Windows via ``module-waveout``.

    Comment ça marche :
        1. On récupère l'IP Windows via ``_get_windows_host_ip()``
        2. On tente ``pactl info`` avec ``PULSE_SERVER=tcp:<IP>``
        3. Si ça répond → c'est PulseAudio Windows, on le retourne
        4. Sinon → None (fallback vers WSLg dans l'appelant)

    Note : WSLg (socket unix ``/mnt/wslg/PulseServer``) est le serveur
    par défaut de WSL2, mais son micro RDPSource ne capte que du silence.
    """
    host_ip = _get_windows_host_ip()
    if host_ip:
        tcp_server = f"tcp:{host_ip}"
        # Teste si PulseAudio Windows est accessible sur le port TCP 4713
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
    """Liste les sources PulseAudio disponibles.

    Exécute ``pactl list sources short`` et parse le résultat en liste
    de dicts ``{"index": int, "name": str}``.

    Retourne une liste vide si la commande échoue (pas de daemon, etc.).
    """
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


# ── Patterns d'identification des sources ─────────────────────────────
# Permet de distinguer les vrais micros des moniteurs et des sources RDP.
_MIC_PATTERNS = ["alsa_input", "usb", "mic", "microphone", "webcam", "capture"]
_RDP_PATTERNS = ["rdpsource", "rdp"]


def _test_source_amplitude(
    source: str, server: str | None = None, duration: float = 1.0
) -> int:
    """Teste un device PulseAudio en capturant ``duration`` secondes.

    Renvoie l'amplitude maximale (int). 0 = silence complet.

    Pourquoi c'est nécessaire :
        PulseAudio peut exposer plusieurs sources (wavein, wavein.2, etc.)
        dont certaines ne captent que du silence. Cette fonction enregistre
        un court extrait et mesure le pic d'amplitude pour déterminer si
        le device capte réellement du son.

    Fonctionnement :
        1. Lance ``parecord`` en arrière-plan avec le device source
        2. Attend que le fichier temporaire ait assez de bytes
        3. Lis les données en int16 et retourne le max absolu
        4. Nettoie le fichier temporaire
    """
    n_samples = int(duration * 16_000)
    expected_bytes = n_samples * 2  # int16 = 2 bytes par échantillon
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
    # Attend que parecord ait écrit assez de données
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
    # Termine parecord proprement
    proc.terminate()
    try:
        proc.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    # Lit les données et calcule l'amplitude max
    try:
        data = np.fromfile(tmp_path, dtype=np.int16, count=n_samples)
    except OSError:
        return 0
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return int(data.max()) if len(data) > 0 else 0


def _pulse_find_input_device(server: str | None = None) -> str | None:
    """Trouve le meilleur device d'entrée PulseAudio (pas un monitor).

    Si plusieurs sources non-monitor existent, teste l'amplitude de chacune
    (~1s par device) et choisit celle qui capte vraiment du son.

    Algorithme :
        1. Liste toutes les sources PulseAudio
        2. Filtre les moniteurs (sortie en boucle) et les sources RDP
        3. S'il n'y a qu'une candidate → la retourne directement
        4. S'il y en a plusieurs → teste l'amplitude de chacune
        5. Retourne celle avec le meilleur score (> 100 = son capté)

    Pourquoi les moniteurs sont exclus :
        ``waveout.monitor`` est le retour audio de la sortie (ce que les
        applications jouent), pas le micro. On ne veut que les sources
        d'entrée (capture).
    """
    candidates: list[str] = []
    rdp_fallback: str | None = None
    for src in _pulse_list_sources(server):
        name = str(src["name"]).lower()
        # Les moniteurs sont les sorties en boucle — on les ignore
        if "monitor" in name:
            continue
        # RDPSource est le micro virtuel WSLg, ne capte que du silence
        if any(p in name for p in _RDP_PATTERNS):
            rdp_fallback = str(src["name"])
            continue
        candidates.append(str(src["name"]))

    if not candidates:
        return rdp_fallback

    # Si un seul device, pas besoin de tester
    if len(candidates) == 1:
        return candidates[0]

    # Teste l'amplitude de chaque candidate (~1s chacune)
    # C'est le seul moyen fiable de savoir lequel capte vraiment du son
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

    # Aucun device ne capte — retourne le premier par défaut
    log.warning("Aucun device ne capte (>100), utilisation de %s", candidates[0])
    return candidates[0]


def _pulse_find_output_device(server: str | None = None) -> str | None:
    """Trouve le meilleur device de sortie PulseAudio.

    Retourne le premier sink disponible via ``pactl list sinks short``.
    Pour PulseAudio Windows, c'est ``waveout`` (le haut-parleur Windows).
    """
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
    L'appelant n'a pas à se soucier du backend — ``record()`` et ``play()``
    dispatchent automatiquement.

    Usage ::
        io = AudioIO()
        audio = io.record(3.0)       # 3 secondes, numpy int16 mono
        io.play(audio)               # relance l'audio
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

        # Détection automatique du backend audio
        # Sous WSL2 avec parecord installé → PulseAudio
        # Sinon → sounddevice (PortAudio)
        self._use_pulse = _is_wsl() and shutil.which("parecord") is not None
        self._pulse_server: str | None = None
        self._pulse_input: str | None = None
        self._pulse_output: str | None = None

        if self._use_pulse:
            # Trouve le serveur PulseAudio (TCP Windows ou WSLg)
            self._pulse_server = _pulse_find_server()
            # Trouve les devices d'entrée/sortie (teste l'amplitude)
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
        """Capture ``duration_seconds`` du micro et renvoie un numpy array int16 mono.

        Le format de sortie est ``(n_samples, 1)`` pour être compatible
        avec soundfile/sounddevice.
        """
        if self._use_pulse:
            return self._record_pulse(duration_seconds)
        return self._record_sounddevice(duration_seconds)

    def _record_sounddevice(self, duration_seconds: float) -> np.ndarray:
        """Capture via sounddevice (PortAudio) — backend Windows natif.

        ``sd.rec()`` est bloquant : il attend la fin de la capture
        avant de retourner le buffer numpy.
        """
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

        Pièges gérés :
            - ``parecord`` n'a pas d'option ``--duration`` sous WSL Debian.
              On poll le taille du fichier et on ``terminate()`` une fois
              assez de données écrites.
            - Le timeout inclut une marge de 5s pour le démarrage du device.
            - Si le fichier fait < 2 bytes, on retourne du silence.
            - Si les données sont courtes (< n_samples), on pad avec des zéros.
        """
        n_samples = int(duration_seconds * self.sample_rate * self.channels)
        if not self._pulse_input:
            log.warning("Aucun device PulseAudio trouvé — retour au silence")
            return np.zeros((n_samples, 1), dtype=np.int16)

        tmp_path = tempfile.mktemp(suffix=".raw")

        # Commande parecord : capture en PCM brut 16 bits, mono, 16 kHz
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

        expected_bytes = n_samples * 2  # 2 bytes par échantillon int16
        timeout = duration_seconds + 5  # marge pour démarrage du device

        # parecord n'a pas d'option --duration sous WSL : on attend qu'il ait
        # écrit assez de données, puis on le termine proprement.
        start = time.monotonic()
        got_size = 0
        try:
            while got_size < expected_bytes:
                if time.monotonic() - start > timeout:
                    log.error("parecord timeout après %.1fs — kill process", timeout)
                    proc.kill()
                    got_size = Path(tmp_path).stat().st_size
                    break
                time.sleep(0.05)  # poll toutes les 50ms
                got_size = Path(tmp_path).stat().st_size
        except FileNotFoundError:
            got_size = 0

        # Termine parecord proprement (SIGTERM → flush → exit)
        proc.terminate()
        try:
            _, stderr_data = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Si SIGTERM ne suffit pas → SIGKILL
            proc.kill()
            proc.wait()
            stderr_data = b""

        if stderr_data:
            log.warning("parecord stderr: %s", stderr_data.decode(errors="replace").strip())

        # Pas de données → silence
        if got_size < 2:
            log.warning("parecord: aucune donnée capturée (%d bytes)", got_size)
            Path(tmp_path).unlink(missing_ok=True)
            return np.zeros((n_samples, 1), dtype=np.int16)

        # Lit les données brutes en int16
        try:
            data = np.fromfile(tmp_path, dtype=np.int16, count=n_samples)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # Pad avec des zéros si la capture est courte
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
        """Joue via sounddevice (PortAudio) — backend Windows natif."""
        sr = sample_rate or self.sample_rate
        sd.play(
            audio,
            samplerate=sr,
            device=self.output_device,
            blocking=True,
        )

    def _play_pulse(self, audio: np.ndarray, sample_rate: int | None = None) -> None:
        """Écrit un WAV temporaire et joue via ``paplay``.

        On ne peut pas envoyer du PCM brut directement à paplay —
        il faut un format avec header (WAV). ``soundfile.write()``
        gère la conversion.
        """
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
        """Lit un fichier WAV (ou tout format supporté par libsndfile).

        Gère automatiquement la conversion stéréo→mono et float→int16
        si nécessaire.
        """
        data, sr = sf.read(str(path))
        if data.ndim > 1 and self.channels == 1:
            # Conversion stéréo → mono par moyennage des canaux
            data = data.mean(axis=1)
        if data.dtype != self.dtype and self.dtype == "int16":
            # Conversion float [-1,1] → int16 [-32768, 32767]
            data = (data * 32767).astype("int16")
        self.play(np.asarray(data), sample_rate=sr)


# ══════════════════════════════════════════════════════════════════════
# Diagnostics et tests
# ══════════════════════════════════════════════════════════════════════


def pulse_diagnostics() -> None:
    """Affiche les diagnostics PulseAudio complets.

    Appelé par ``python -m hal_voice --diagnose``.
    Affiche :
        - Le serveur PulseAudio détecté
        - La liste des sources avec identification (micro/monitor/RDP)
        - Le device sélectionné automatiquement
        - Un test de capture de 3s avec mesure d'amplitude
    """
    if not _is_wsl():
        print("Pas sous WSL2 — skip diagnostics PulseAudio")
        return

    print("=== Diagnostics PulseAudio (WSL2) ===\n")

    # Détection du serveur PulseAudio Windows
    server = _pulse_find_server()
    if server:
        print(f"[OK] PulseAudio Windows détecté : {server}")
    else:
        print("[INFO] PulseAudio Windows non trouvé — utilisation WSLg (défaut)")
        print("  → Le micro WSLg (RDPSource) ne capture que du silence")
        print("  → Installe PulseAudio Windows + configure PULSE_SERVER")

    print()

    # Test pulseaudio daemon avec le serveur trouvé
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

    # Lister toutes les sources avec un marqueur de type
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

    # Affiche le device sélectionné automatiquement
    io = AudioIO()
    print(f"Device sélectionné : {io._pulse_input}")
    print(f"Device output      : {io._pulse_output}")
    print()

    # Test capture 3s — le micro Windows met parfois du temps à s'activer
    print("Test capture 3s...")
    audio = io.record(3.0)
    max_amp = int(np.abs(audio).max())
    print(f"  shape={audio.shape}, max_amplitude={max_amp}")
    if max_amp < 100:
        print("  → Faible amplitude — vérifie PulseAudio Windows + PULSE_SERVER")
    else:
        print("  → Son capté OK")


def quick_test() -> None:
    """Boucle 5s : record 3s, replay, affiche devices. Pour test manuel.

    S'exécute via ``python -m hal_voice.audio_io``.
    """
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
