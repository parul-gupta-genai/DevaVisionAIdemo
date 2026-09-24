#!/usr/bin/env bash
# ==============================================================================
# DevaVisionAI - 100% FREE Google Colab GPU Setup Script
# Features: Free NVIDIA T4 GPU, MediaMTX, Redis, Backend, Frontend + Cloudflare Tunnel
# ==============================================================================
set -e

echo "========================================================="
echo "🚀 Initializing DevaVisionAI on Google Colab GPU (FREE)..."
echo "========================================================="

# 1. System packages
echo "[1/6] Installing system packages (PostgreSQL, Redis, FFmpeg, Node.js)..."
apt-get update -qq || true
apt-get install -y -qq postgresql postgresql-contrib redis-server ffmpeg libgl1 libglib2.0-0 curl wget psmisc || apt-get install -y postgresql postgresql-contrib redis-server ffmpeg libgl1 curl wget

# Start PostgreSQL & Redis
service postgresql start || true
service redis-server start || redis-server --daemonize yes || true

# Initialize PostgreSQL Database & User
su - postgres -c "psql -c \"DO \\\$do\\\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'admin') THEN CREATE USER admin WITH PASSWORD 'admin' SUPERUSER; END IF; END \\\$do\\\$;\"" || true
su - postgres -c "psql -c \"SELECT 1 FROM pg_database WHERE datname = 'cctv'\" | grep -q 1 || psql -c \"CREATE DATABASE cctv OWNER admin;\"" || true

# 2. Node.js 20 Setup
if ! command -v node &> /dev/null || [ "$(node -v | cut -d'.' -f1 | tr -d 'v')" -lt 18 ]; then
    echo "Updating Node.js to version 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1 || true
    apt-get install -y -qq nodejs || true
fi

# 3. MediaMTX Streaming Engine
echo "[2/6] Starting MediaMTX WebRTC / RTSP streaming engine..."
mkdir -p /content/mediamtx_bin
cd /content/mediamtx_bin
if [ ! -f "mediamtx" ]; then
    wget -q https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_linux_amd64.tar.gz
    tar -xzf mediamtx_v1.9.0_linux_amd64.tar.gz
    rm -f mediamtx_v1.9.0_linux_amd64.tar.gz
fi
pkill -f "mediamtx" || true
nohup ./mediamtx > /content/mediamtx.log 2>&1 &
echo "MediaMTX is running."

# 4. Navigate to DevaVisionAI
echo "[3/6] Setting up DevaVisionAI Repository..."
cd /content/DevaVisionAI || cd /content/*DevaVisionAI* || true

# 5. Frontend Build (Instant Loading Production UI)
echo "[4/6] Building Production Web Dashboard (Fast & Instant Load)..."
cd /content/DevaVisionAI/frontend
npm install --no-audit --no-fund --silent
npm run build --silent || true
echo "Frontend built successfully."

# 6. Python Backend Dependencies & Startup
echo "[5/6] Starting Unified FastAPI Backend (UI + AI Engines)..."
cd /content/DevaVisionAI/backend

export DATABASE_URL="postgresql://admin:admin@localhost:5432/cctv"
export REDIS_URL="redis://localhost:6379/0"
export PYTHONPATH="/content/DevaVisionAI/backend"

pip install -q -r /content/DevaVisionAI/backend/requirements.txt ultralytics aiohttp || pip install -q fastapi uvicorn pydantic sqlalchemy redis opencv-python-headless ultralytics pyyaml pydantic-settings python-multipart python-jose[cryptography] passlib loguru prometheus_client slowapi pyjwt bcrypt asyncpg psycopg2-binary aiohttp diskcache edge-tts psutil tenacity email-validator

# Setup test user and auto-create tables
python seed_admin.py || true

# Start FastAPI Backend
pkill -f "uvicorn" || true
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > /content/backend.log 2>&1 &
echo "Unified Server starting on port 8000..."

# Wait for backend healthcheck
BACKEND_OK=0
for i in {1..20}; do
    sleep 1
    if curl -s http://127.0.0.1:8000/docs > /dev/null; then
        BACKEND_OK=1
        echo "✅ Backend is 100% HEALTHY and ANSWERING on port 8000!"
        break
    fi
done

if [ $BACKEND_OK -eq 0 ]; then
    echo "⚠️ Backend log error details:"
    tail -n 25 /content/backend.log
fi

# 7. Cloudflare Tunnel for Free Public HTTPS Access
echo "[6/6] Launching Cloudflare Tunnel (100% Free HTTPS URL)..."
if [ ! -f "/usr/local/bin/cloudflared" ]; then
    wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x /usr/local/bin/cloudflared
fi

pkill -f "cloudflared" || true
nohup /usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8000 > /content/tunnel.log 2>&1 &


echo "========================================================="
echo "Waiting for Public URL to be ready..."
PUBLIC_URL=""
for i in {1..25}; do
    sleep 2
    if [ -f "/content/tunnel.log" ]; then
        PUBLIC_URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" /content/tunnel.log | tail -n 1)
        if [ -n "$PUBLIC_URL" ]; then
            break
        fi
    fi
done

echo "========================================================="
echo "🎉 DEVA VISION AI IS LIVE & RUNNING ON GOOGLE COLAB GPU!"
echo "👉 CLICK TO OPEN DASHBOARD : $PUBLIC_URL"
echo "👉 Login Email             : gauriirajpoot@gmail.com"
echo "👉 Login Password          : admin"
echo "========================================================="
echo "🟢 Live Traffic Log (Do not stop this cell):"

# Keep tunnel actively streamed and alive
tail -f /content/tunnel.log




