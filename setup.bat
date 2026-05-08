@echo off
cd /d "%~dp0"
echo ============================================================
echo  OT-2 Protocol Assistant - First-Time Setup
echo ============================================================
echo.

REM ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    pause & exit /b 1
)

REM ── Main venv ─────────────────────────────────────────────────
echo [1/4] Creating main virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat
echo [2/4] Installing dependencies...
pip install -r requirements.txt --quiet
echo        Done.

REM ── Opentrons venv ────────────────────────────────────────────
echo [3/4] Creating Opentrons virtual environment (for simulation)...
python -m venv venv_ot
.\venv_ot\Scripts\pip.exe install opentrons --quiet
echo        Done.

REM ── Write OT_VENV_PYTHON into .env ────────────────────────────
echo [4/4] Configuring .env...

REM Get absolute path to venv_ot python
for /f "delims=" %%i in ('powershell -command "(Resolve-Path '.\venv_ot\Scripts\python.exe').Path.Replace('\','/')"') do set OT_PYTHON=%%i

REM Check if .env exists
if exist .env (
    REM Check if OT_VENV_PYTHON already set
    findstr /c:"OT_VENV_PYTHON" .env >nul 2>&1
    if errorlevel 1 (
        echo OT_VENV_PYTHON="%OT_PYTHON%">> .env
        echo        Added OT_VENV_PYTHON to existing .env
    ) else (
        echo        OT_VENV_PYTHON already present in .env
    )
) else (
    echo GEMINI_API_KEY="">> .env
    echo OT_VENV_PYTHON="%OT_PYTHON%">> .env
    echo.
    echo  !! ACTION REQUIRED: Open .env and add your Gemini API key:
    echo     GEMINI_API_KEY="your_key_here"
    echo     Get a free key at: https://aistudio.google.com/api-keys
)

echo.
echo ============================================================
echo  Setup complete!
echo  Next: double-click launch.bat to start the app.
echo ============================================================
echo.
pause
