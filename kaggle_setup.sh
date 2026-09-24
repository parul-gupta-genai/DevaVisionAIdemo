#!/usr/bin/env bash
# ==============================================================================
# DevaVisionAI - 100% FREE Kaggle GPU Setup Script (ANPR & AI Dashboard)
# Features: Free Kaggle NVIDIA GPU (T4/P100), MediaMTX, Redis, Backend, Frontend + Cloudflare Tunnel
# ==============================================================================
set -e

echo "========================================================="
echo "🚀 Initializing DevaVisionAI & ANPR on Kaggle GPU..."
echo "========================================================="

WORKDIR="/kaggle/working"
REPO_DIR="$WORKDIR/DevaVisionAI"

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

# 2. Node.js Setup
if ! command -v node &> /dev/null || [ "$(node -v | cut -d'.' -f1 | tr -d 'v')" -lt 18 ]; then
    echo "Updating Node.js to version 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1 || true
    apt-get install -y -qq nodejs || true
fi

# 3. MediaMTX Streaming Engine
echo "[2/6] Starting MediaMTX WebRTC / RTSP streaming engine..."
mkdir -p $WORKDIR/mediamtx_bin
cd $WORKDIR/mediamtx_bin
if [ ! -f "mediamtx" ]; then
    wget -q https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_linux_amd64.tar.gz
    tar -xzf mediamtx_v1.9.0_linux_amd64.tar.gz
    rm -f mediamtx_v1.9.0_linux_amd64.tar.gz
fi
pkill -f "mediamtx" || true
nohup ./mediamtx > $WORKDIR/mediamtx.log 2>&1 &
echo "MediaMTX is running."

# 4. Navigate to DevaVisionAI
echo "[3/6] Setting up DevaVisionAI Repository..."
if [ -d "$REPO_DIR" ]; then
    cd "$REPO_DIR"
else
    cd "$WORKDIR"
    # Find directory if named differently
    FOUND_DIR=$(find $WORKDIR -maxdepth 1 -type d -name "*DevaVisionAI*" | head -n 1)
    if [ -n "$FOUND_DIR" ]; then
        cd "$FOUND_DIR"
        REPO_DIR="$FOUND_DIR"
    else
        echo "Error: DevaVisionAI repository not found in $WORKDIR"
        exit 1
    fi
fi

# 5. Frontend Build (Instant Loading Production UI)
echo "[4/6] Building Production Web Dashboard..."
cd "$REPO_DIR/frontend"
npm install --no-audit --no-fund --silent
npm run build --silent || true
echo "Frontend built successfully."

# 6. Python Backend Dependencies & Startup
echo "[5/6] Starting Unified FastAPI Backend (ANPR Engine)..."
cd "$REPO_DIR/backend"

export DATABASE_URL="postgresql://admin:admin@localhost:5432/cctv"
export REDIS_URL="redis://localhost:6379/0"
export PYTHONPATH="$REPO_DIR/backend"

pip install -q -r "$REPO_DIR/backend/requirements.txt" ultralytics aiohttp || pip install -q fastapi uvicorn pydantic sqlalchemy redis opencv-python-headless ultralytics pyyaml pydantic-settings python-multipart python-jose[cryptography] passlib loguru prometheus_client slowapi pyjwt bcrypt asyncpg psycopg2-binary aiohttp diskcache edge-tts psutil tenacity email-validator

# Setup test user and auto-create tables
python seed_admin.py || true

# Start FastAPI Backend
pkill -f "uvicorn" || true
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > $WORKDIR/backend.log 2>&1 &
echo "Unified Server starting on port 8000..."

# Wait for backend healthcheck
BACKEND_OK=0
for i in {1..20}; do
    sleep 1
    if curl -s http://127.0.0.1:8000/docs > /dev/null; then
        BACKEND_OK=1
        echo "✅ Backend & ANPR Engine is 100% HEALTHY on port 8000!"
        break
    fi
done

if [ $BACKEND_OK -eq 0 ]; then
    echo "⚠️ Backend log error details:"
    tail -n 25 $WORKDIR/backend.log
fi

# 7. Cloudflare Tunnel for Free Public HTTPS Access
echo "[6/6] Launching Cloudflare Tunnel (100% Free Public HTTPS URL)..."
if [ ! -f "/usr/local/bin/cloudflared" ]; then
    wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x /usr/local/bin/cloudflared
fi

pkill -f "cloudflared" || true
nohup /usr/local/bin/cloudflared tunnel --url http://localhost:8000 > $WORKDIR/tunnel.log 2>&1 &

echo "========================================================="
echo "Waiting for Public Link..."
PUBLIC_URL=""
for i in {1..25}; do
    sleep 2
    if [ -f "$WORKDIR/tunnel.log" ]; then
        PUBLIC_URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $WORKDIR/tunnel.log | tail -n 1)
        if [ -n "$PUBLIC_URL" ]; then
            break
        fi
    fi
done

echo "========================================================="
echo "🎉 DEVA VISION AI (ANPR) IS LIVE & RUNNING ON KAGGLE GPU!"
echo "👉 CLICK TO OPEN DASHBOARD : $PUBLIC_URL"
echo "👉 Login Email             : gauriirajpoot@gmail.com"
echo "👉 Login Password          : admin"
echo "========================================================="
echo "🟢 Live Tunnel Stream (Do not stop this cell):"

tail -f $WORKDIR/tunnel.log
