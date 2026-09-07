# get-default-mic.ps1 — Renvoie l'index WaveIn du micro par défaut Windows.
#
# C'est la façon fiable de connaître le device que l'utilisateur a sélectionné
# dans Paramètres > Son > Entrée : on interroge l'API Core Audio (MMDevice)
# pour obtenir le micro de capture par défaut, puis on le retrouve dans la
# liste des devices WaveIn (module-waveout de PulseAudio).
#
# Une autre approche (tester chaque micro en mesurant l'amplitude) échoue :
# - elle teste des devices périmés/muets et ne devine pas le choix utilisateur ;
# - le micro par défaut peut ne pas être exposé du tout dans PulseAudio si
#   halvoice.pa pointe sur un autre index.
#
# Sorties (une par ligne, clé=valeur) :
#   index=<N>     index WaveIn du micro par défaut (0 = wavein, 1 = wavein.2, ...)
#   name=<...>    nom "friendly" exposé par Windows (MMDevice)
#   szpname=<...> nom waveInGetDevCaps du device trouvé (identique à la
#                 description "WaveIn on <szpname>" dans PulseAudio)
#
# Options :
#   -IndexOnly  n'affiche que l'index (pratique pour les .bat / for /f)
#
# Retour : sortie vide + code 0 si aucun micro par défaut n'est trouvé.

[CmdletBinding()]
param(
    [switch]$IndexOnly
)

$ErrorActionPreference = "Stop"

# ── Interop WinMM : waveInGetNumDevs / waveInGetDevCaps ──────────────
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct WaveInCapsProbe {
    public ushort wMid;
    public ushort wPid;
    public uint vDriverVersion;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string szPname;
    public uint dwFormats;
    public ushort wChannels;
    public ushort wReserved;
}

public static class WinMmProbe {
    [DllImport("winmm.dll")]
    public static extern uint waveInGetNumDevs();
    [DllImport("winmm.dll")]
    public static extern uint waveInGetDevCaps(uint uDeviceID, ref WaveInCapsProbe pwic, uint cbwic);
}
'@

# ── Interop Core Audio : micro de capture par défaut (MMDevice) ───────
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceProbe {
    int a();
    int o();
    int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
}

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumeratorProbe {
    int f();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDeviceProbe endpoint);
}

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MmDeviceEnumeratorComObject { }

public static class MmDeviceProbe {
    public static string DefaultCaptureId() {
        var enumerator = (IMMDeviceEnumeratorProbe)(new MmDeviceEnumeratorComObject());
        IMMDeviceProbe endpoint;
        Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(1, 1, out endpoint));
        string id;
        Marshal.ThrowExceptionForHR(endpoint.GetId(out id));
        return id;
    }
}
'@

# ── 1. Micro de capture par défaut (friendly name via le registre) ────
$defaultName = $null
try {
    $defaultId = [MmDeviceProbe]::DefaultCaptureId()
    $defaultName = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Enum\SWD\MMDEVAPI\$defaultId" -ErrorAction Stop).FriendlyName
} catch {
    if ($IndexOnly) {
        Write-Output ""
    }
    exit 0
}

# ── 2. Liste des devices WaveIn (ceux que module-waveout peut exposer) ─
$waveIn = [System.Collections.Generic.List[object[]]]::new()
$count = [WinMmProbe]::waveInGetNumDevs()
for ($i = 0; $i -lt $count; $i++) {
    $caps = New-Object WaveInCapsProbe
    [void][WinMmProbe]::waveInGetDevCaps([uint32]$i, [ref]$caps, [uint32][System.Runtime.InteropServices.Marshal]::SizeOf([type][WaveInCapsProbe]))
    $waveIn.Add(@($i, [string]$caps.szPname))
}

if ($count -eq 0) {
    if ($IndexOnly) { Write-Output "" }
    exit 0
}

# ── 3. Score de similarité entre deux noms (insensible aux accents/maj) ─
function Get-NameScore([string]$a, [string]$b) {
    $normA = (($a.ToLowerInvariant()) -replace '[^a-z0-9\u00e0-\u00ff ]', ' ')
    $normB = (($b.ToLowerInvariant()) -replace '[^a-z0-9\u00e0-\u00ff ]', ' ')
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

# ── 4. Choix du device WaveIn le plus proche du micro par défaut ──────
$bestIndex = -1
$bestName = ""
$bestScore = 0.0
foreach ($dev in $waveIn) {
    $idx = [int]$dev[0]
    $nm = [string]$dev[1]
    $score = Get-NameScore $defaultName $nm
    if ($score -gt $bestScore) {
        $bestScore = $score
        $bestIndex = $idx
        $bestName = $nm
    }
}

if ($bestIndex -lt 0) {
    if ($IndexOnly) { Write-Output "" }
    exit 0
}

if ($IndexOnly) {
    Write-Output $bestIndex
} else {
    Write-Output ("index=" + $bestIndex)
    Write-Output ("name=" + $defaultName)
    Write-Output ("szpname=" + $bestName)
}