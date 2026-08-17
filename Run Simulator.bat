@echo off
title Sim Pedal Calibrator - simulator
cd /d "%~dp0"

py --version >nul 2>nul
if errorlevel 1 goto nopython

py -c "import serial" >nul 2>nul
if errorlevel 1 (
    echo Installing pyserial. This only happens once...
    py -m pip install --user pyserial
    echo.
)

py run_app.py --simulate
if errorlevel 1 pause
exit /b

:nopython
echo.
echo   Python is not installed on this PC yet.
echo.
echo   1. Go to  https://www.python.org/downloads/
echo   2. Click the big yellow "Download Python" button and run the installer
echo   3. IMPORTANT: on the first installer screen, tick
echo      "Add python.exe to PATH" before clicking Install Now
echo   4. When it finishes, double-click this file again
echo.
pause
