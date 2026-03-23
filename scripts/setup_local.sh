#!/usr/bin/env bash
# Setup script for the local machine — run once after cloning the repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo " Anki Agent — Local Machine Setup"
echo "============================================"

# 1. Check Python
echo ""
echo "[1/5] Checking Python version..."
PYTHON=$(command -v python3 || true)
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: python3 not found."
    exit 1
fi
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Found: Python $PY_VERSION"

# 2. Virtual environment
echo ""
echo "[2/5] Creating virtual environment..."
cd "$PROJECT_DIR"
$PYTHON -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
echo "  Done."

# 3. Config
echo ""
echo "[3/5] Config check..."
if [[ ! -f "$PROJECT_DIR/config.yaml" ]]; then
    cp "$PROJECT_DIR/config.example.yaml" "$PROJECT_DIR/config.yaml"
    echo "  Created config.yaml from example — EDIT IT with your VPS details."
else
    echo "  config.yaml already exists."
fi

# 4. Directories
echo ""
echo "[4/5] Creating logs directory..."
mkdir -p "$PROJECT_DIR/logs"
echo "  Done."

# 5. Test AnkiConnect
echo ""
echo "[5/5] Testing AnkiConnect..."
if ./venv/bin/python local_sync.py --test-anki 2>/dev/null; then
    echo "  AnkiConnect OK."
else
    echo "  AnkiConnect not available (Anki may not be open — that's fine for setup)."
fi

# Print cron suggestion
echo ""
echo "Suggested cron entry (run: crontab -e):"
echo ""
echo "  # Anki Agent — sync cards every 30 minutes"
echo "  */30 * * * * cd $PROJECT_DIR && ./venv/bin/python local_sync.py >> logs/local_sync.log 2>&1"
echo ""
echo "============================================"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "   1. Edit config.yaml with your VPS host, user, key path"
echo "   2. Test VPS: python local_sync.py --test-vps"
echo "   3. Simulate full pipeline: make simulate"
echo "   4. Add the cron entry above (crontab -e)"
echo "============================================"
