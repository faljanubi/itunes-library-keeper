@echo off
rem One-time setup: creates a private Python environment with pywin32.
cd /d "%~dp0"
py -3 -m venv .venv || python -m venv .venv
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
echo.
echo Done. Start the app with "iTunes Library Keeper.cmd".
pause
