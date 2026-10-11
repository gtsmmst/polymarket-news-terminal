@echo off
REM Start the Polymarket News Terminal on http://127.0.0.1:8001
REM Creates a local virtualenv on first run and installs dependencies.
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtualenv in .venv ...
  python -m venv .venv
)
set PY=.venv\Scripts\python.exe

"%PY%" -m pip install -q -r requirements.txt

echo ===================================================
echo   Polymarket News Terminal
echo   Open in browser:  http://127.0.0.1:8001
echo   First cycle pulls markets + news (~30-60 s),
echo   then press "Refresh News + Score" or just wait.
echo   Stop with Ctrl+C or close this window
echo ===================================================

start "" http://127.0.0.1:8001
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
echo.
echo --- terminal stopped ---
pause
