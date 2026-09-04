@echo off
REM hal-voice installer — Windows
setlocal

echo === hal-voice — Installation ===

REM ── 1. Python venv ──────────────────────────────────────────────────
echo.
echo [1/3] Création du virtual environment...

if exist ".venv\Scripts\activate.bat" (
    echo   OK — venv existant détecté.
) else (
    python -m venv .venv
    echo   OK — venv créé.
)
call .venv\Scripts\activate.bat

REM ── 2. Dépendances Python ──────────────────────────────────────────
echo.
echo [2/3] Installation des dépendances Python...
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install -e . -q
echo   OK — packages installés.

REM ── 3. Vérification ────────────────────────────────────────────────
echo.
echo [3/3] Vérification...

python -c "import sounddevice" 2>nul || (echo   X sounddevice manquant & exit /b 1)
python -c "import vosk"        2>nul || (echo   X vosk manquant & exit /b 1)
python -c "import win32com"    2>nul || (echo   X pywin32 manquant & exit /b 1)
python -c "import pynput"      2>nul || (echo   X pynput manquant & exit /b 1)
echo   OK — tous les modules Python sont importables.

REM ── Modèle Vosk ────────────────────────────────────────────────────
set MODEL_DIR=models\vosk-model-small-fr-0.22
if exist "%MODEL_DIR%" (
    echo   OK — modèle Vosk FR présent.
) else (
    echo   Téléchargement du modèle Vosk FR...
    mkdir models 2>nul
    powershell -Command "Invoke-WebRequest -Uri 'https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip' -OutFile 'models\vosk-model.zip'"
    powershell -Command "Expand-Archive -Path 'models\vosk-model.zip' -DestinationPath 'models' -Force"
    del models\vosk-model.zip
    echo   OK — modèle Vosk FR installé.
)

echo.
echo === Installation terminée ! ===
echo Lance hal-voice avec : scripts\run.bat
