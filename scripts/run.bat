@echo off
REM ══════════════════════════════════════════════════════════════════════
REM run.bat — Lanceur hal-voice pour Windows
REM
REM Ce script :
REM   1. Se place à la racine du projet
REM   2. Active le venv Python s'il existe
REM   3. Lance ``python -m hal_voice`` depuis le dossier src/
REM
REM Utilisation :
REM   scripts\run.bat
REM
REM Notes :
REM   - Le venv doit être installé (scripts\install.bat)
REM   - Sous WSL2, utilisez ./scripts/run.sh à la place
REM ══════════════════════════════════════════════════════════════════════
@echo off
setlocal

REM Se place à la racine du projet (parent du dossier scripts/)
cd /d "%~dp0\.."

REM Active le venv s'il existe
REM Le venv isole les packages Python de l'installation système
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Lance l'assistant depuis src/ pour que le package soit trouvé
cd src
python -m hal_voice

REM En cas d'erreur, affiche un message et attend une touche
if %errorlevel% neq 0 (
    echo.
    echo [Erreur] Hal a rencontre un probleme.
    pause
)
