@echo off
REM ============================================================
REM  ANNADATA OS — One-Click Start (Universal)
REM ============================================================
REM  Runs everything in SQLite mode (no Docker) by default.
REM ============================================================

echo.
echo ============================================================
echo   ANNADATA OS — One-Click Startup (Root)
echo ============================================================
echo.

cd /d "%~dp0"

REM Handle fast startup flag
if "%1"=="--fast" (
    echo [START] Fast startup initiated - skipping setup...
    goto :start_services
)

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

REM Check if Node.js is available
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH.
    echo Please install Node.js 20+ from https://nodejs.org
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [SETUP] Creating Python virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo [SETUP] Activating Python virtual environment...
call venv\Scripts\activate.bat

REM Install/Verify Python dependencies
echo [SETUP] Verifying Python dependencies... this may take a minute
if exist "requirements.txt" (
    pip install -r requirements.txt
) else (
    echo [WARNING] requirements.txt not found, skipping dependency sync.
)

REM Install frontend dependencies if needed
echo [SETUP] Checking frontend dependencies...
if not exist "frontend\node_modules" (
    echo [SETUP] Installing frontend dependencies - npm install...
    cd frontend
    call npm install
    cd ..
)

:start_services
echo.
echo [START] Launching all services in SQLite mode...
echo.

REM Start the orchestrator (with USE_SQLITE=True via orchestration)
call venv\Scripts\activate.bat 2>nul
python orchestrator.py

pause
