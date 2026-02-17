#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found. Please install Python 3."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in .venv ..."
  python3 -m venv .venv
fi

source ".venv/bin/activate"

if ! python -m pip show twilio >/dev/null 2>&1 || ! python -m pip show python-dotenv >/dev/null 2>&1; then
  echo "Installing dependencies from requirements.txt ..."
  python -m pip install -r requirements.txt
fi

echo "Starting diet reminder bot ..."
exec python diet_reminder_bot.py
