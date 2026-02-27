#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Create venv if it doesn't exist ──────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# ── Activate venv ─────────────────────────────────────────────────────────────
source "$VENV_DIR/bin/activate"
echo "Virtual environment activated: $(which python)"

# ── Install / upgrade dependencies ───────────────────────────────────────────
echo "Installing requirements..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# ── Export all vars from .env ─────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    echo "Exporting environment variables from .env ..."
    set -o allexport
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +o allexport
else
    echo "WARNING: .env file not found at $ENV_FILE"
fi

# ── Move to project root ──────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

# ── Run the server ────────────────────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-4021}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL_LOWER="$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"
RELOAD_FLAG=""
[ "$APP_ENV" = "development" ] && RELOAD_FLAG="--reload"

echo ""
echo "Starting Kairos Agent..."
echo "  Host    : $HOST"
echo "  Port    : $PORT"
echo "  Workers : $WORKERS"
echo "  Env     : ${APP_ENV:-development}"
echo "──────────────────────────────────────────────"

if [ "$WORKERS" -gt 1 ]; then
    # Multi-worker production mode via gunicorn
    exec gunicorn app.main:app \
        -k uvicorn.workers.UvicornWorker \
        --workers "$WORKERS" \
        --bind "$HOST:$PORT" \
        --log-level "$LOG_LEVEL_LOWER"
else
    exec uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        $RELOAD_FLAG \
        --log-level "$LOG_LEVEL_LOWER"
fi
