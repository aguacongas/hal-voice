@echo off
REM hal-voice launcher — Windows
setlocal enabledelayedexpansion

echo [Hal] Initialisation des systemes...

REM On se place dans le dossier src pour que le module hal_voice soit importable
cd /d "%~dp0\..\src"

REM Lancement via le module Python
python -m hal_voice

if %errorlevel% neq 0 (
    echo.
    echo [Erreur] Hal a rencontre un probleme lors du demarrage.
    pause
)

echo [Hal] Systemes eteints.
pause
