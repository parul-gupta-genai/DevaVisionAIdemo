@echo off
echo ==========================================================
echo  Stopping DevaVisionAI Services on Windows
echo ==========================================================

echo Stopping Docker infrastructure (TimescaleDB, Redis, MediaMTX)...
docker compose stop

echo.
echo ==========================================================
echo  DevaVisionAI Docker services stopped cleanly!
echo  (Note: You can close the Backend and Frontend terminal windows)
echo ==========================================================
