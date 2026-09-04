<#
.SYNOPSIS
    Detects which WaveIn device captures audio, updates halvoice.pa,
    restarts PulseAudio. Uses brute-force test per device.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File detect-mic.ps1
#>

$ErrorActionPreference = "Stop"

$pulseDir = Join-Path $env:LOCALAPPDATA "pulseaudio\pulseaudio"
$paExe    = Join-Path $pulseDir "bin\pulseaudio.exe"
$paFile   = Join-Path $pulseDir "etc\halvoice.pa"
$paBak    = "$paFile.bak"

# Path to the test script in WSL
$projectDir = Split-Path $PSScriptRoot
$wslProject = "/mnt/" + $projectDir.Substring(0,1).ToLower() + $projectDir.Substring(2) -replace '\\','/'
$testScript = "$wslProject/scripts/test-mic-device.sh"

# ── 1. Enumerate WaveIn devices ────────────────────────────────────────
Write-Host "[1/3] Enumerating WaveIn devices..."

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

# ── 2. Test each device ────────────────────────────────────────────────
Write-Host "[2/3] Testing each device..."

# Backup config
if (-not (Test-Path $paBak)) {
    Copy-Item $paFile $paBak -Force
}

$paContent = Get-Content $paFile -Raw
$bestIndex = -1
$bestMax = 0

# Get host IP from WSL (more reliable than PowerShell Get-NetRoute)
$hostIP = (wsl.exe -d Ubuntu -- ip route show default 2>$null) -split '\s+' | Select-Object -Index 2
if (-not $hostIP) {
    Write-Host "  Pas d'IP host detectee."
    exit 1
}
Write-Host "  Host IP: $hostIP"

foreach ($dev in $deviceList) {
    $idx = $dev.Index
    Write-Host -NoNewline "  [$idx] $($dev.Name) -> "

    # Update halvoice.pa with this index
    $newContent = [regex]::Replace(
        $paContent,
        "load-module module-waveout[^\r\n]*",
        "load-module module-waveout sink_name=waveout source_name=wavein record=1 input_device=$idx"
    )
    Set-Content $paFile $newContent -NoNewline

    # Restart PulseAudio
    Stop-Process -Name pulseaudio -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $pidFiles = Get-ChildItem "$env:USERPROFILE\.config\pulse\*-runtime\pid" -ErrorAction SilentlyContinue
    foreach ($pf in $pidFiles) { Remove-Item $pf.FullName -Force -ErrorAction SilentlyContinue }

    Start-Process -FilePath $paExe -ArgumentList "-F", $paFile -WindowStyle Hidden
    Start-Sleep -Seconds 3

    # Check PulseAudio is running
    $paProc = Get-Process -Name pulseaudio -ErrorAction SilentlyContinue
    if (-not $paProc) {
        Write-Host "FAIL (PulseAudio not running)"
        continue
    }

    # Test via WSL bash script
    $ampStr = wsl.exe -d Ubuntu -- bash "$testScript" "$hostIP" "$idx" 2>$null
    $maxAmp = [int]($ampStr -replace '[^\d\-]', '')

    Write-Host "max=$maxAmp"

    if ($maxAmp -gt $bestMax) {
        $bestMax = $maxAmp
        $bestIndex = $idx
    }

    if ($maxAmp -gt 100) {
        Write-Host "  >>> DEVICE CAPTURANT TROUVE: index $idx (max=$maxAmp)"
        break
    }
}

# ── 3. Finalize ────────────────────────────────────────────────────────
Write-Host "[3/3] Finalization..."

if ($bestIndex -eq -1) {
    Write-Host "  Aucun device ne capte du son."
    if (Test-Path $paBak) { Copy-Item $paBak $paFile -Force }
    exit 1
}

# Write final config
$finalContent = [regex]::Replace(
    (Get-Content $paFile -Raw),
    "load-module module-waveout[^\r\n]*",
    "load-module module-waveout sink_name=waveout source_name=wavein record=1 input_device=$bestIndex"
)
Set-Content $paFile $finalContent -NoNewline
Write-Host "  input_device=$bestIndex -> $paFile"

# Final restart
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
