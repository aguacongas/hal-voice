@echo off
setlocal
REM ══════════════════════════════════════════════════════════════════════
REM teardown.bat — Désinstallation de hal-voice depuis Windows
REM
REM Ce script supprime :
REM   1. PulseAudio for Windows + config + autostart
REM   2. Venv + modèle Vosk dans WSL (via uninstall.sh)
REM   3. (Optionnel) WSL2 + Ubuntu
REM
REM Utilisation :
REM   scripts\teardown.bat              (safe — garde WSL2)
REM   scripts\teardown.bat --full       (tout supprimer, y compris WSL2)
REM   scripts\teardown.bat --check      (affiche ce qui serait supprimé)
REM ══════════════════════════════════════════════════════════════════════
@echo off
setlocal

cd /d "%~dp0\.."
set "PROJECT_DIR=%CD%"
set "FULL_REMOVE=0"
set "CHECK_ONLY=0"

if "%~1"=="--full" set FULL_REMOVE=1
if "%~1"=="--check" set CHECK_ONLY=1
if "%~1"=="--help" (
    echo Utilisation : scripts\teardown.bat [--full] [--check]
    echo   --full   Supprime aussi WSL2 + Ubuntu
    echo   --check  Affiche ce qui serait supprime sans rien faire
    exit /b 0
)

echo ========================================
echo   hal-voice -- Teardown Windows
echo ========================================
echo.

REM ══════════════════════════════════════════════════════════════════════
REM 1. Autostart PulseAudio
REM ══════════════════════════════════════════════════════════════════════
echo [1/4] Autostart PulseAudio...

set "STARTUP_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PulseAudio hal-voice.bat"

if exist "%STARTUP_LINK%" (
    if %CHECK_ONLY% equ 1 (
        echo   ! A supprimer : %STARTUP_LINK%
    ) else (
        del "%STARTUP_LINK%"
        echo   OK -- autostart supprime.
    )
) else (
    echo   OK -- rien a faire.
)

REM ══════════════════════════════════════════════════════════════════════
REM 2. PulseAudio for Windows
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [2/4] PulseAudio for Windows...

set "PA_DIR=%LOCALAPPDATA%\pulseaudio"

if exist "%PA_DIR%" (
    if %CHECK_ONLY% equ 1 (
        echo   ! A supprimer : %PA_DIR%
    ) else (
        REM Arrête PulseAudio s'il tourne
        tasklist /FI "IMAGENAME eq pulseaudio.exe" 2>nul | findstr /i "pulseaudio" >nul
        if not errorlevel 1 (
            echo   Arret de PulseAudio...
            taskkill /F /IM pulseaudio.exe >nul 2>&1
        )

        REM Supprime le runtime PulseAudio (PID files stale)
        del /q "%USERPROFILE%\.config\pulse\*-runtime\pid" >nul 2>&1

        REM Supprime le dossier PulseAudio
        rmdir /s /q "%PA_DIR%" >nul 2>&1
        echo   OK -- PulseAudio supprime.
    )
) else (
    echo   OK -- PulseAudio absent.
)

REM ══════════════════════════════════════════════════════════════════════
REM 3. Fichiers Linux (venv, modèle, cache)
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [3/4] Fichiers Linux...

if exist "%PROJECT_DIR%\.venv" (
    if %CHECK_ONLY% equ 1 (
        echo   ! A supprimer : .venv
    ) else (
        rmdir /s /q "%PROJECT_DIR%\.venv" >nul 2>&1
        echo   OK -- venv supprime.
    )
)

if exist "%PROJECT_DIR%\models\vosk-model-small-fr-0.22" (
    if %CHECK_ONLY% equ 1 (
        echo   ! A supprimer : models\vosk-model-small-fr-0.22
    ) else (
        rmdir /s /q "%PROJECT_DIR%\models\vosk-model-small-fr-0.22" >nul 2>&1
        echo   OK -- modele Vosk supprime.
    )
)

REM ══════════════════════════════════════════════════════════════════════
REM 4. WSL2 + Ubuntu (--full uniquement)
REM ══════════════════════════════════════════════════════════════════════
echo.
echo [4/4] WSL2...

if %FULL_REMOVE% equ 0 (
    echo   WSL2 conserve. Utilise --full pour le supprimer.
) else (
    if %CHECK_ONLY% equ 1 (
        echo   ! A supprimer : WSL2 + Ubuntu
    ) else (
        echo   Suppression de la distro Ubuntu...
        wsl --unregister Ubuntu >nul 2>&1
        echo   OK -- Ubuntu supprime.

        echo   Suppression de WSL2...
        dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart >nul 2>&1
        dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart >nul 2>&1
        echo   OK -- WSL2 desactive.
        echo.
        echo   *** REDERMARRAGE REQUIS ***
        echo   Redemarre ton PC pour finaliser la desinstallation.
        shutdown /r /t 10 /c "Redemarrage requis pour desactiver WSL2"
    )
)

REM ══════════════════════════════════════════════════════════════════════
REM Résumé
REM ══════════════════════════════════════════════════════════════════════
echo.
if %CHECK_ONLY% equ 1 (
    echo ========================================
    echo   Verification terminee (rien supprime)
    echo ========================================
) else (
    echo ========================================
    echo   Desinstallation terminee !
    echo ========================================
    if %FULL_REMOVE% equ 1 (
        echo   Redemarre ton PC pour finaliser WSL2.
    ) else (
        echo   Relance l'installation : scripts\setup.bat
    )
)
