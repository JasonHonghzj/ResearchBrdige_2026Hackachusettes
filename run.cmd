@echo off
setlocal
cd /d "%~dp0"
set "DEMO_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "DEMO_PYTHON=.venv\Scripts\python.exe"
"%DEMO_PYTHON%" -c "import fastapi, uvicorn, sklearn, reportlab" >nul 2>&1
if errorlevel 1 (
    echo Install Python and dependencies first: python -m pip install -r requirements.txt
    echo See README.md for setup instructions.
    pause
    exit /b 1
)
echo ResearchBridge: http://127.0.0.1:8000
echo Keep this window open. Press Ctrl+C to stop.
"%DEMO_PYTHON%" -m uvicorn app:app --host 127.0.0.1 --port 8000
if errorlevel 1 pause
