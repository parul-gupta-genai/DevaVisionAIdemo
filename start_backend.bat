@echo off
REM Detached backend launcher for Windows.

cd /d "%~dp0backend"
if errorlevel 1 exit /b 1

if "%DATABASE_URL%"=="" set "DATABASE_URL=postgresql://admin:admin@localhost:5433/cctv"
if "%REDIS_URL%"=="" set "REDIS_URL=redis://localhost:6379/0"
set "PYTHONPATH=%~dp0backend"

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
) else (
    python -m uvicorn main:app --host 127.0.0.1 --port 8000
)
