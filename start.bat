@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
    echo Python not found. Please install Python 3.11.
    pause
    exit /b 1
)
python -m pip install -r requirements.txt >nul 2>&1
start "" pythonw main.py
