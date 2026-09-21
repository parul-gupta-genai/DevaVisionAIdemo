#!/bin/bash
# ==============================================================================
# DevaVisionAI Master Startup Script (NVIDIA Jetson Nano / Orin / Linux)
# Starts: TimescaleDB + Redis + MediaMTX + Backend + DeepStream + Frontend
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Every child inherits this. The default soft limit of 1024 fds is exhausted
# at ~16 cameras (roughly 50-60 fds each across decoders, encoders, GPU
# handles and RTSP sockets), and the resulting failures masquerade as GPU/VIC
# capacity errors rather than fd exhaustion. See deepstream_pyds/run_forever.sh.
ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn)" 2>/dev/null || true
cd "$DIR"

echo "=========================================================="
echo " 🚀 Starting DevaVisionAI Platform on NVIDIA Jetson"
echo "=========================================================="

# 1. Cleanup old instances and processes
echo "1/6 Cleaning up any lingering processes on ports 8000, 3000..."
pkill -9 -f "uvicorn" 2>/dev/null || true
# Kill the DS relauncher BEFORE the pipeline it babysits, or it respawns it.
pkill -9 -f "run_forever.sh" 2>/dev/null || true
# DeepStream runs as plain "python3 main.py" (its cwd is deepstream_pyds/),
# so kill it by process cwd — a cmdline pattern never matches it.
for dsp in $(pgrep -f "python3 main.py" 2>/dev/null); do [[ "$(readlink /proc/$dsp/cwd 2>/dev/null)" == *deepstream_pyds* ]] && kill -9 $dsp; done; true
pkill -9 -f "vite" 2>/dev/null || true
# Kill stale ffmpeg->MediaMTX relays from a previous run — orphaned relays
# keep publishing raw_* paths and fight the fresh ones for the publisher slot.
# ([r] bracket keeps pkill from matching this script's own command line.)
pkill -9 -f "8554/[r]aw_" 2>/dev/null || true
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 1

# 2. Start Infrastructure Containers (TimescaleDB, Redis, MediaMTX)
echo "2/6 Ensuring Docker infrastructure is running..."
sudo docker compose up -d timescaledb redis mediamtx 2>/dev/null || docker compose up -d timescaledb redis mediamtx 2>/dev/null || true

echo "Waiting for database and redis to be ready..."
for i in {1..15}; do
    if docker compose exec -T timescaledb pg_isready -U admin -d cctv >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

# Ensure vector extension exists before migrations
docker compose exec -T timescaledb psql -U admin -d cctv -c "CREATE EXTENSION IF NOT EXISTS vector;" || true

# 3. Apply Database Migrations
echo "3/6 Running Database Migrations..."
cd "$DIR/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv --copies .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

export DATABASE_URL="postgresql://admin:admin@localhost:5433/cctv"
export REDIS_URL="redis://localhost:6379/0"
export PYTHONPATH="$DIR/backend:$PYTHONPATH"

alembic upgrade head

# 4. Check & Build TensorRT Engine if missing
cd "$DIR"
ENGINE_FILE="$DIR/backend/detection/yolo11n_opset12.onnx_b30_gpu0_fp16.engine"
if [ ! -f "$ENGINE_FILE" ]; then
    if [ -f "build_and_benchmark.sh" ]; then
        echo "4/6 TensorRT engine missing. Building FP16 dynamic engine (Batch 30)..."
        chmod +x build_and_benchmark.sh
        ./build_and_benchmark.sh || true
    fi
else
    echo "4/6 TensorRT engine is ready ($ENGINE_FILE)."
fi

# 5. Launch Services
echo "5/6 Launching Platform Services..."

LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"

# Cleanup trap on Ctrl+C or script exit
cleanup() {
    echo ""
    echo "=========================================================="
    echo " 🛑 Shutting down DevaVisionAI Platform..."
    echo "=========================================================="
    kill $(jobs -p) 2>/dev/null || true
    pkill -f "uvicorn" 2>/dev/null || true
    pkill -9 -f "run_forever.sh" 2>/dev/null || true
    for dsp in $(pgrep -f "python3 main.py" 2>/dev/null); do [[ "$(readlink /proc/$dsp/cwd 2>/dev/null)" == *deepstream_pyds* ]] && kill -9 $dsp; done; true
    pkill -f "vite" 2>/dev/null || true
    pkill -9 -f "8554/[r]aw_" 2>/dev/null || true
    echo "All processes stopped cleanly."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Start Backend API
cd "$DIR/backend"
source .venv/bin/activate
export PYTHONPATH="$DIR/backend:$PYTHONPATH"
uvicorn main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "  -> Backend API started on port 8000 (PID: $BACKEND_PID)"

# Start DeepStream Pipeline (if available) via the auto-relaunch wrapper —
# it self-heals the pipeline after a fatal trunk error (NVMM buffer wedge).
if [ -d "$DIR/deepstream_pyds" ] && [ -f "$DIR/deepstream_pyds/main.py" ]; then
    cd "$DIR/deepstream_pyds"
    export PYTHONPATH="$DIR/backend:$DIR/deepstream_pyds:$PYTHONPATH"
    bash run_forever.sh > "$LOG_DIR/deepstream.log" 2>&1 &
    DS_PID=$!
    echo "  -> DeepStream Engine started with auto-relaunch (PID: $DS_PID)"
fi

# Start Frontend
cd "$DIR/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run dev -- --host 0.0.0.0 --port 3000 > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "  -> Frontend Dashboard started on port 3000 (PID: $FRONTEND_PID)"

# 6. Display Success Banner
JETSON_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=========================================================="
echo " ✅ DEVAVISIONAI PLATFORM IS FULLY RUNNING!"
echo "=========================================================="
echo " 🌐 Web Dashboard:   http://${JETSON_IP}:3000  (or http://localhost:3000)"
echo " 🔌 Backend API:     http://${JETSON_IP}:8000  (docs: http://${JETSON_IP}:8000/docs)"
echo " 📹 MediaMTX WHEP:   http://${JETSON_IP}:8889 / http://${JETSON_IP}:8189"
echo " 📋 Logs Directory:  $LOG_DIR/"
echo "=========================================================="
echo " Press Ctrl+C at any time to stop all services cleanly."
echo "=========================================================="

# Block the script from exiting so background processes stay alive.
# (If you want to view logs, you can open another terminal and run: tail -f logs/backend.log logs/frontend.log)
wait
