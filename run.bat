@echo off
title DriveAlert - AI Driver Drowsiness Detection
color 0A
echo.
echo  ============================================================
echo    DriveAlert - AI Driver Drowsiness Detection System
echo    Works on ANY device, ANY network (Wi-Fi / 4G / 5G)
echo  ============================================================
echo.

REM -- Check Python --
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python 3.10 or higher from:
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)

REM -- Create venv if missing --
if not exist venv (
    echo [1/3] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/3] Virtual environment ready.
)

REM -- Run setup (installs packages + downloads model) --
echo [2/3] Checking packages and model...
venv\Scripts\python.exe setup.py
if errorlevel 1 (
    echo.
    echo [ERROR] Setup failed. See messages above.
    pause
    exit /b 1
)

REM -- Open browser automatically --
echo [3/3] Starting DriveAlert server...
echo.
echo  ============================================================
echo    LOCAL ACCESS:     http://127.0.0.1:5000
echo    For mobile/external: double-click  share_mobile.bat
echo  ============================================================
echo.
timeout /t 2 >nul
start "" http://127.0.0.1:5000

venv\Scripts\python.exe app.py
echo.
echo [Server stopped]
pause
