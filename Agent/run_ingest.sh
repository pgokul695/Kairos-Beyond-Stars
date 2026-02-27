#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

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

# ── Run ingest (dry-run by default; pass args to override) ───────────────────
cd "$SCRIPT_DIR"

ARGS="${@:---csv data/zomato.csv --dry-run}"

echo ""
echo "Running: python scripts/ingest.py $ARGS"
echo "──────────────────────────────────────────────"
python scripts/ingest.py $ARGS
