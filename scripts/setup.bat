@echo off
setlocal enabledelayedexpansion
REM ══════════════════════════════════════════════════════════════════════
REM setup.bat — Installation complète hal-voice depuis Windows
REM
REM Ce script installe TOUT en une seule commande :
REM   1. WSL2 + Ubuntu (si pas encore installé)
REM   2. PulseAudio for Windows (micro via TCP 4713)
REM   3. Dépendances Linux via install.sh dans WSL
REM
REM Utilisation :
REM   scripts\setup.bat              (lance l'installation)
REM   scripts\setup.bat --check      (vérifie sans installer)
REM
REM Prérequis :
REM   - Windows 10 2004+ ou Windows 11
REM   - Droits administrateur (pour activer WSL2)
REM   - Connexion internet
REM ══════════════════════════════════════════════════════════════════════
@echo off
setlocal

cd /d "%~dp0\.."
set "PROJECT_DIR=%CD%"
set "CHECK_ONLY=0"

if "%~1"=="--check" set CHECK_ONLY=1
if "%~1"=="--help" (
    echo Utilisation : scripts\setup.bat [--check]
    echo   --check   Verifie sans rien installer
    exit /b 0
)

echo ========================================
echo   hal-voice — Setup Windows + WSL2
echo ========================================
echo.

REM ══════════════════════════════════════════════════════════════════════
REM 1. Vérification des droits admin
REM ══════════════════════════════════════════════════════════════════════
echo [1/5] Verification des droits...

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   ! Droits administrateur requis pour installer WSL2.
    echo   Fais clic-droit sur setup.bat et choisis "Exécuter en tant qu'administrateur".
    exit /b 1
)
echo   OK -- droits administrateur.

REM ══════════════════════════════════════════════════════════════════════
REM 2. WSL2 + Ubuntu
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [2/5] WSL2 + Ubuntu...

wsl --status >nul 2>&1
if %errorlevel% equ 0 (
    echo   OK -- WSL2 deja installe.
) else (
    if %CHECK_ONLY% equ 1 (
        echo   ! WSL2 non installe.
    ) else (
        echo   Installation de WSL2 + Ubuntu...
        wsl --install -d Ubuntu --no-launch
        if %errorlevel% neq 0 (
            echo   Echec installation WSL2.
            echo   Verifie que Windows est a jour (Windows 10 2004+ ou Windows 11).
            exit /b 1
        )
        echo   OK -- WSL2 + Ubuntu installe.
        echo.
        echo   *** REDERMARRAGE REQUIS ***
        echo   Redemarre ton PC puis relance setup.bat pour continuer.
        shutdown /r /t 10 /c "Redemarrage requis pour WSL2 -- hal-voice"
        exit /b 0
    )
)

REM Vérifie que la distro Ubuntu est disponible
wsl -l -v 2>nul | findstr /i "Ubuntu" >nul
if %errorlevel% neq 0 (
    if %CHECK_ONLY% equ 0 (
        echo   Installation de la distro Ubuntu...
        wsl --install -d Ubuntu
    ) else (
        echo   ! Distro Ubuntu non installe.
    )
)

REM ══════════════════════════════════════════════════════════════════════
REM 3. PulseAudio for Windows
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [3/5] PulseAudio for Windows...

set "PA_DIR=%LOCALAPPDATA%\pulseaudio\pulseaudio"
set "PA_EXE=%PA_DIR%\bin\pulseaudio.exe"

if exist "%PA_EXE%" (
    echo   OK -- PulseAudio deja installe.
) else (
    if %CHECK_ONLY% equ 1 (
        echo   ! PulseAudio non installe.
    ) else (
        echo   Telechargement de PulseAudio (pgaskin build)...
        set "PA_URL=https://github.com/pgaskin/pulseaudio-win32/releases/download/v5/pulseaudio.zip"
        set "PA_ZIP=%TEMP%\pulseaudio.zip"

        powershell -NoProfile -Command ^
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PA_URL%' -OutFile '%PA_ZIP%'"

        if not exist "%PA_ZIP%" (
            echo   Echec du telechargement.
            exit /b 1
        )

        echo   Extraction...
        powershell -NoProfile -Command ^
            "Expand-Archive -Path '%PA_ZIP%' -DestinationPath '%LOCALAPPDATA%\pulseaudio' -Force"
        del "%PA_ZIP%"

        if exist "%PA_EXE%" (
            echo   OK -- PulseAudio installe.
        ) else (
            echo   Echec de l'installation.
            exit /b 1
        )
    )
)

REM ══════════════════════════════════════════════════════════════════════
REM 4. Config PulseAudio
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [4/5] Config PulseAudio...

set "PA_CONF_DIR=%PA_DIR%\etc"
set "HALVOICE_PA=%PA_CONF_DIR%\halvoice.pa"

if exist "%HALVOICE_PA%" (
    echo   OK -- Config existante.
) else (
    if %CHECK_ONLY% equ 1 (
        echo   ! Config PulseAudio absente.
    ) else (
        echo   Creation de la config...

        REM Créer le dossier etc s'il n'existe pas
        if not exist "%PA_CONF_DIR%" mkdir "%PA_CONF_DIR%"

        REM halvoice.pa — config PulseAudio pour hal-voice
        (
            echo # halvoice.pa -- PulseAudio config for hal-voice
            echo # Expose le micro Windows via TCP 4713 pour WSL2
            echo.
            echo # Micro Windows via WaveOut
            echo load-module module-waveout sink_name=waveout source_name=wavein record=1 input_device=2
            echo.
            echo # Protocol TCP (accessible depuis WSL2)
            echo load-module module-native-protocol-tcp auth-anonymous=1
            echo.
            echo # Ne pas s'arreter quand inactif
            echo --exit-idle-time=-1
        ) > "%HALVOICE_PA%"

        REM Default.pa — sans module-waveout (évite les doublons)
        set "DEFAULT_PA=%PA_CONF_DIR%\pulse\default.pa"
        if not exist "%PA_CONF_DIR%\pulse" mkdir "%PA_CONF_DIR%\pulse"
        (
            echo # default.pa -- PulseAudio default config (hal-voice)
            echo # module-waveout est charge par halvoice.pa avec input_device
            echo.
            echo load-module module-native-protocol-unix
            echo load-module module-always-sink null-sink
        ) > "%DEFAULT_PA%"

        echo   OK -- Config creee.
    )
)

REM ══════════════════════════════════════════════════════════════════════
REM 4b. Raccourci autostart
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [4b/5] Autostart PulseAudio...

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_LINK=%STARTUP_DIR%\PulseAudio hal-voice.bat"

if exist "%STARTUP_LINK%" (
    echo   OK -- Autostart deja configure.
) else (
    if %CHECK_ONLY% equ 0 (
        (
            echo @echo off
            echo start "" "%PA_EXE%" -F "%HALVOICE_PA%"
        ) > "%STARTUP_LINK%"
        echo   OK -- Autostart cree.
    )
)

REM ══════════════════════════════════════════════════════════════════════
REM 5. Install.sh dans WSL
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [5/5] Installation des dependances Linux...

if %CHECK_ONLY% equ 1 (
    wsl -d Ubuntu -- bash -c "cd /mnt/c/%PROJECT_DIR:\=/% && bash scripts/install.sh --check"
) else (
    echo   Lance install.sh dans WSL...
    wsl -d Ubuntu -- bash -c "cd /mnt/c/%PROJECT_DIR:\=/% && bash scripts/install.sh"
)

REM ══════════════════════════════════════════════════════════════════════
REM Résumé
REM ══════════════════════════════════════════════════════════════════════
echo.
echo ========================================
echo   Installation terminee !
echo ========================================
echo.
echo Lance hal-voice avec :
echo   - Windows : scripts\run.bat
echo   - WSL2    : wsl -d Ubuntu -- bash scripts/run.sh
echo.
echo PulseAudio demarrera automatiquement au prochain login.
