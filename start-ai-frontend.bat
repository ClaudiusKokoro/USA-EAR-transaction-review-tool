@echo off
setlocal
title EAR AI Assistant Frontend
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python environment not found.
  echo Run install-dependencies.bat first.
  pause
  exit /b 1
)

echo Starting the EAR AI Assistant frontend on http://localhost:8502
echo Keep this window open while you use the tool. Close it to stop the server.

start "EAR AI Assistant" /d "%CD%" cmd /k ".venv\Scripts\python.exe -m streamlit run app\ai_main.py --server.headless true --server.showEmailPrompt false --server.port 8502 --browser.gatherUsageStats false"
timeout /t 6 /nobreak >nul
start "" "http://localhost:8502"
exit
