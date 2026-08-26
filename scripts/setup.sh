#!/usr/bin/env bash
# Setup: install dependencies (+ optional engines) into the current environment.
#   ./scripts/setup.sh            core only
#   ./scripts/setup.sh full       + playwright chromium (browser engines)
set -e
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}

echo "==> Installing core dependencies..."
$PYTHON -m pip install -r requirements.txt

echo "==> Ensuring face models..."
$PYTHON scripts/download_models.py

if [ "${1:-}" = "full" ]; then
  echo "==> Installing Playwright + Chromium (browser engines)..."
  $PYTHON -m pip install playwright
  $PYTHON -m playwright install chromium
fi

echo "==> Done. Start the app with:  python run.py"
