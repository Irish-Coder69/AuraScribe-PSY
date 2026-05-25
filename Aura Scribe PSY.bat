@echo off
cd /d "%~dp0"

echo ============================================================
echo  DEVELOPER LAUNCH SCRIPT - Requires Python on this machine
echo  End users should run the installed Aura Scribe PSY.exe
echo ============================================================
echo.

if not exist main.py (
    echo.
    echo ERROR: main.py was not found in this folder.
    echo.
    pause
    exit /b 1
)

echo Starting Aura Scribe PSY (debug mode)...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Could not start Aura Scribe PSY.
    echo Make sure Python 3.10+ is installed and on your PATH.
    echo.
    pause
)