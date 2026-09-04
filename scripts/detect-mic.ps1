<#
.SYNOPSIS
    Détecte automatiquement quel device WaveIn capture du son,
    met à jour halvoice.pa avec le bon input_device,
    et redémarre PulseAudio.

.DESCRIPTION
    Ce script résout le problème de l'index WaveIn qui varie par machine.
    Il teste chaque device WaveIn en enregistrant réellement du son via
    parecord (WSL) et mesure l'amplitude pour trouver le bon.

    Le script PowerShell gère la partie Windows (WaveIn, PulseAudio),
    et délègue le test audio à un script bash WSL (test-mic-device.sh).

    Pourquoi un test brut est nécessaire :
        - Les noms WaveIn sont tronqués à 32 caractères
        - L'ordre des devices varie par machine
        - Le bon device n'est pas forcément celui par défaut Windows
        - La meilleure façon de tester est d'enregistrer et de mesurer

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File detect-mic.ps1

.NOTES
    Nécessite :
        - PulseAudio for Windows (pgaskin) installé
        - WSL2 Ubuntu avec pulseaudio-utils
        - numpy dans le venv WSL
#>

$ErrorActionPreference = "Stop"

# ── Configuration ─────────────────────────────────────────────────────
# Chemins d'installation de PulseAudio for Windows
$pulseDir = Join-Path $env:LOCALAPPDATA "pulseaudio\pulseaudio"
$paExe    = Join-Path $pulseDir "bin\pulseaudio.exe"
$paFile   = Join-Path $pulseDir "etc\halvoice.pa"
$paBak    = "$paFile.bak"

# Chemin vers le script bash de test dans WSL
# On convertit le chemin Windows du projet en chemin WSL (/mnt/c/...)
$projectDir = Split-Path $PSScriptRoot
$wslProject = "/mnt/" + $projectDir.Substring(0,1).ToLower() + $projectDir.Substring(2) -replace '\\','/'
$testScript = "$wslProject/scripts/test-mic-device.sh"

# ══════════════════════════════════════════════════════════════════════
# ÉTAPE 1 : Énumération des devices WaveIn
# ══════════════════════════════════════════════════════════════════════

Write-Host "[1/3] Enumerating WaveIn devices..."

# Code C# inline pour appeler l'API Windows WaveIn via P/Invoke.
# On utilise Add-Type pour compiler le code à la volée.
# waveInGetNumDevs() retourne le nombre de devices d'entrée.
# waveInGetDevCaps() retourne les informations d'un device (nom, canaux, etc.)
$csharpSource = @"
using System;
using System.Runtime.InteropServices;

public class WaveInHelper {
    [DllImport("winmm.dll")]
    public static extern int waveInGetNumDevs();

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern int waveInGetDevCaps(int id, out WAVEINCAPS caps, int size);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct WAVEINCAPS {
        public int wMid;
        public int wPid;
        public int vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szPname;
        public int dwFormats;
        public short wChannels;
        public short wReserved1;
    }
}
"@

Add-Type -TypeDefinition $csharpSource

# Énumère tous les devices WaveIn et affiche leur nom
$numDevs = [WaveInHelper]::waveInGetNumDevs()
$caps = New-Object WaveInHelper+WAVEINCAPS
$deviceList = @()

for ($i = 0; $i -lt $numDevs; $i++) {
    [WaveInHelper]::waveInGetDevCaps($i, [ref]$caps, [System.Runtime.InteropServices.Marshal]::SizeOf($caps)) | Out-Null
    $deviceList += @{ Index = $i; Name = $caps.szPname }
    Write-Host "  [$i] $($caps.szPname)"
}

if ($deviceList.Count -eq 0) {
    Write-Host "  Aucun device WaveIn."
    exit 1
}

# ══════════════════════════════════════════════════════════════════════
# ÉTAPE 2 : Test de chaque device
# ══════════════════════════════════════════════════════════════════════

Write-Host "[2/3] Testing each device..."

# Sauvegarde de la config PulseAudio avant modification
if (-not (Test-Path $paBak)) {
    Copy-Item $paFile $paBak -Force
}

$paContent = Get-Content $paFile -Raw
$bestIndex = -1
$bestMax = 0

# Récupère l'IP Windows depuis WSL (plus fiable que Get-NetRoute PowerShell
# qui peut retourner la mauvaise route si VPN/multi-interfaces)
$hostIP = (wsl.exe -d Ubuntu -- ip route show default 2>$null) -split '\s+' | Select-Object -Index 2
if (-not $hostIP) {
    Write-Host "  Pas d'IP host detectee."
    exit 1
}
Write-Host "  Host IP: $hostIP"

# Pour chaque device WaveIn, on :
#   1. Met à jour halvoice.pa avec input_device=<index>
#   2. Redémarre PulseAudio pour appliquer le changement
#   3. Lance test-mic-device.sh depuis WSL qui enregistre 2s et mesure l'amplitude
#   4. Si l'amplitude > 100, c'est le bon device
foreach ($dev in $deviceList) {
    $idx = $dev.Index
    Write-Host -NoNewline "  [$idx] $($dev.Name) -> "

    # Met à jour halvoice.pa avec le nouvel input_device
    $newContent = [regex]::Replace(
        $paContent,
        "load-module module-waveout[^\r\n]*",
        "load-module module-waveout sink_name=waveout source_name=wavein record=1 input_device=$idx"
    )
    Set-Content $paFile $newContent -NoNewline

    # Redémarre PulseAudio pour appliquer la nouvelle config
    Stop-Process -Name pulseaudio -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    # Nettoie les PID files stale (empêche "Daemon already running")
    $pidFiles = Get-ChildItem "$env:USERPROFILE\.config\pulse\*-runtime\pid" -ErrorAction SilentlyContinue
    foreach ($pf in $pidFiles) { Remove-Item $pf.FullName -Force -ErrorAction SilentlyContinue }

    # Lance PulseAudio en arrière-plan
    Start-Process -FilePath $paExe -ArgumentList "-F", $paFile -WindowStyle Hidden
    Start-Sleep -Seconds 3

    # Vérifie que PulseAudio a bien démarré
    $paProc = Get-Process -Name pulseaudio -ErrorAction SilentlyContinue
    if (-not $paProc) {
        Write-Host "FAIL (PulseAudio not running)"
        continue
    }

    # Teste la capture via le script bash WSL
    # Le script lance parecord pendant 2s et retourne l'amplitude max
    $ampStr = wsl.exe -d Ubuntu -- bash "$testScript" "$hostIP" "$idx" 2>$null
    $maxAmp = [int]($ampStr -replace '[^\d\-]', '')

    Write-Host "max=$maxAmp"

    if ($maxAmp -gt $bestMax) {
        $bestMax = $maxAmp
        $bestIndex = $idx
    }

    # Si on trouve un device qui capte, on arrête immédiatement
    if ($maxAmp -gt 100) {
        Write-Host "  >>> DEVICE CAPTURANT TROUVE: index $idx (max=$maxAmp)"
        break
    }
}

# ══════════════════════════════════════════════════════════════════════
# ÉTAPE 3 : Finalisation
# ══════════════════════════════════════════════════════════════════════

Write-Host "[3/3] Finalization..."

if ($bestIndex -eq -1) {
    Write-Host "  Aucun device ne capte du son."
    # Restaure la config de backup
    if (Test-Path $paBak) { Copy-Item $paBak $paFile -Force }
    exit 1
}

# Écrit la config finale avec le bon input_device
$finalContent = [regex]::Replace(
    (Get-Content $paFile -Raw),
    "load-module module-waveout[^\r\n]*",
    "load-module module-waveout sink_name=waveout source_name=wavein record=1 input_device=$bestIndex"
)
Set-Content $paFile $finalContent -NoNewline
Write-Host "  input_device=$bestIndex -> $paFile"

# Redémarrage final de PulseAudio avec la config correcte
Stop-Process -Name pulseaudio -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$pidFiles = Get-ChildItem "$env:USERPROFILE\.config\pulse\*-runtime\pid" -ErrorAction SilentlyContinue
foreach ($pf in $pidFiles) { Remove-Item $pf.FullName -Force -ErrorAction SilentlyContinue }
Start-Process -FilePath $paExe -ArgumentList "-F", $paFile -WindowStyle Hidden
Start-Sleep -Seconds 3

$np = Get-Process -Name pulseaudio -ErrorAction SilentlyContinue
if ($np) { Write-Host "  PulseAudio redemarre (PID $($np.Id))" }

Write-Host "`n=== Termine ==="
Write-Host "Relance depuis WSL: ./scripts/run.sh --diagnose"
