@echo off
setlocal
title Install Dependencies
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Could not create the virtual environment.
  echo Install Python 3.10 or newer, then run this file again.
  pause
  exit /b 1
)

echo Installing / updating dependencies. This needs internet access.
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Done. Start the tool with start-windows.bat or start-all.bat.
pause
