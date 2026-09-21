#!/bin/bash
# Detached backend launcher.
#
# Start it with:
#     setsid nohup bash start_backend.sh >> logs/backend.log 2>&1 < /dev/null &
#
# uvicorn started as a plain child of an interactive ssh session dies when that
# session is reaped, which looks exactly like a crash: the API stops answering
# and nothing in the log says why. setsid detaches it from the terminal so it
# survives. Note this launches the API only — the analytics plugins run inside
# the DeepStream process (deepstream_pyds/run_forever.sh), so plugin changes
# need that restarted too, not this.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/backend" || exit 1

export DATABASE_URL="${DATABASE_URL:-postgresql://admin:admin@localhost:5433/cctv}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export PYTHONPATH="$DIR/backend"

# Matches run_forever.sh — see the note there on why 1024 fds is not enough.
ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn)" 2>/dev/null || true

exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
