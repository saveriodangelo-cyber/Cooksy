@echo off
setlocal EnableExtensions EnableDelayedExpansion
set RICETTEPDF_OLLAMA_MODEL= llama3.1-2k
set RICETTEPDF_OLLAMA_TIMEOUT_S=240
set "DISABLE_MODEL_SOURCE_CHECK=True"
set "PADDLEX_HOME=%CD%\data\paddlex"
set "PADDLE_HOME=%CD%\data\paddle"


cd /d "%~dp0"

echo [RicettePDF] Avvio...



REM 1) Venv
if not exist ".venv\Scripts\python.exe" (
  echo [RicettePDF] Creo virtualenv...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [ERRORE] Impossibile creare la venv. Installa Python 3 e riprova.
    pause
    exit /b 1
  )
)

REM 2) Attiva venv
call ".venv\Scripts\activate.bat"

REM 3) Dipendenze
if exist "requirements.txt" (
  echo [RicettePDF] Installo/aggiorno dipendenze...
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
)

REM 4) Avvio UI (HTML via pywebview)
echo [RicettePDF] Avvio interfaccia...
python -m app.launcher

if errorlevel 1 (
  echo.
  echo [ERRORE] Avvio fallito
  pause
  exit /b 1s
)

endlocal
