@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please create the project environment first. See README_RESEARCHBRIDGE.md.
    pause
    exit /b 1
)
echo ResearchBridge: http://127.0.0.1:8501
echo Keep this window open while using the app. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

