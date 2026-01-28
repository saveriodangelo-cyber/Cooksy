@echo off
REM Cooksy Desktop: Launcher automatico per sviluppo
REM Avvia API + Frontend + Browser in modalità dev

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ============================================================
echo  Cooksy Development Server
echo ============================================================
echo.

REM Colori (se supportati)
set GREEN=[92m
set YELLOW=[93m
set RED=[91m
set RESET=[0m

REM Controlla se Python esiste
python --version > nul 2>&1
if errorlevel 1 (
    echo Error: Python not found in PATH
    exit /b 1
)

REM Controlla venv
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Attiva venv
call .venv\Scripts\activate.bat

REM Installa dipendenze se mancano
pip list | find "Flask" > nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -q Flask Flask-CORS
)

REM Lancia API in background
echo Starting API Server on http://localhost:5000
start "Cooksy API" cmd /k python -m backend.api_rest

REM Aspetta che API sia pronto
timeout /t 3 /nobreak

REM Lancia frontend HTTP server
echo Starting Frontend on http://localhost:8000
start "Cooksy Frontend" cmd /k python -m http.server 8000 -d ui

REM Aspetta che frontend sia pronto
timeout /t 2 /nobreak

REM Apri browser
echo Opening browser...
start http://localhost:8000

echo.
echo ============================================================
echo  Development servers running!
echo ============================================================
echo.
echo  Frontend:  http://localhost:8000
echo  API:       http://localhost:5000/api/health
echo.
echo  Press Ctrl+C in each window to stop
echo.

pause
