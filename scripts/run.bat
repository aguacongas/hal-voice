@echo off
setlocal

REM hal-voice launcher — Windows
cd /d "%~dp0\.."

REM Active le venv s'il existe
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

cd src
python -m hal_voice

if %errorlevel% neq 0 (
    echo.
    echo [Erreur] Hal a rencontre un probleme.
    pause
)
