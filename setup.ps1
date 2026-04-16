# ============================================================
# ANNADATA OS — Root Setup Script
# ============================================================
# Run this ONCE to set up the entire project.
# After setup, use start-all.bat to run.
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ANNADATA OS — Root Project Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

# 1. Check prerequisites
Write-Host "[CHECK] Python..." -ForegroundColor Yellow
try { python --version } catch { 
    Write-Host "ERROR: Python not found. Install Python 3.11+" -ForegroundColor Red
    exit 1 
}

Write-Host "[CHECK] Node.js..." -ForegroundColor Yellow
try { node --version } catch { 
    Write-Host "ERROR: Node.js not found. Install Node.js 20+" -ForegroundColor Red
    exit 1 
}

# 2. Create Python virtual environment
if (!(Test-Path "venv")) {
    Write-Host "[SETUP] Creating Python virtual environment..." -ForegroundColor Green
    python -m venv venv
}

# 3. Activate and install
Write-Host "[SETUP] Activating virtual environment..." -ForegroundColor Green
& .\venv\Scripts\Activate.ps1

Write-Host "[SETUP] Installing Python dependencies (Universal)..." -ForegroundColor Green
pip install -r requirements.txt

# 4. Create SQLite database with all tables
Write-Host "[SETUP] Initializing database (annadata.db)..." -ForegroundColor Green
$env:USE_SQLITE="True"
python -c "import asyncio, sys; sys.path.insert(0, '.'); from services.shared.db.session import init_db; from services.shared.db.models import *; asyncio.run(init_db()); print('Database initialized successfully!')"

# 5. Install frontend dependencies
Write-Host "[SETUP] Installing frontend dependencies..." -ForegroundColor Green
Set-Location frontend
npm install
Set-Location ..

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "  Run 'start-all.bat' to launch all services without Docker." -ForegroundColor Green
Write-Host "  Or use 'docker compose up --build' for Postgres/Redis mode." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
