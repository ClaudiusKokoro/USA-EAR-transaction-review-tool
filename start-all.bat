@echo off
setlocal
title EAR Tools
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python environment not found.
  echo Run install-dependencies.bat first.
  pause
  exit /b 1
)

echo Starting both tools ...
echo   Review workbench: http://localhost:8501
echo   AI assistant:     http://localhost:8502

start "EAR Review Workbench" /d "%CD%" cmd /k ".venv\Scripts\python.exe -m streamlit run app\main.py --server.headless true --server.showEmailPrompt false --server.port 8501 --browser.gatherUsageStats false"
start "EAR AI Assistant" /d "%CD%" cmd /k ".venv\Scripts\python.exe -m streamlit run app\ai_main.py --server.headless true --server.showEmailPrompt false --server.port 8502 --browser.gatherUsageStats false"
timeout /t 7 /nobreak >nul
start "" "http://localhost:8501"
start "" "http://localhost:8502"
exit
