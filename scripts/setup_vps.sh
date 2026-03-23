#!/usr/bin/env bash
# Setup script for the VPS — run once after cloning the repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo " Anki Agent — VPS Setup"
echo "============================================"

# 1. Check Python
echo ""
echo "[1/5] Checking Python version..."
PYTHON=$(command -v python3 || true)
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Found: Python $PY_VERSION"
if [[ "${PY_VERSION%.*}" -lt 3 ]] || [[ "${PY_VERSION#*.}" -lt 10 ]]; then
    echo "ERROR: Python 3.10+ required."
    exit 1
fi

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
    echo "  Created config.yaml from example — EDIT IT before running."
else
    echo "  config.yaml already exists."
fi
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "  Created .env from example — ADD YOUR API KEY."
else
    echo "  .env already exists."
fi

# 4. Directories
echo ""
echo "[4/5] Creating logs directory..."
mkdir -p "$PROJECT_DIR/logs"
echo "  Done."

# 5. Cron suggestion
echo ""
echo "[5/5] Suggested cron entry (run: crontab -e):"
echo ""
echo "  # Anki Agent — generate cards daily at 03:00"
echo "  0 3 * * * cd $PROJECT_DIR && ./venv/bin/python vps_generate.py >> logs/vps_generate.log 2>&1"
echo ""
echo "============================================"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "   1. Edit config.yaml with your topic instructions and settings"
echo "   2. Edit .env with your API key"
echo "   3. Test: python vps_generate.py --test-connection"
echo "   4. Dry run: python vps_generate.py --dry-run"
echo "   5. Add the cron entry above (crontab -e)"
echo "============================================"
