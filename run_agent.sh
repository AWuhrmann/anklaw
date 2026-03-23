#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_agent.sh — Daily Claude Code agent runner (VPS cron entry point)
#
# This script spins up a Claude Code agent that autonomously:
#   1. Reads your research topics
#   2. Checks existing cards to avoid duplicates
#   3. Searches the web for current information
#   4. Generates and ingests new Anki cards
#
# Usage:
#   bash run_agent.sh              # normal daily run
#   bash run_agent.sh --dry-run    # print agent prompt without running
#   bash run_agent.sh --check      # verify claude CLI + config, then exit
#
# Prerequisites (on VPS):
#   - Claude Code CLI installed:  npm install -g @anthropic-ai/claude-code
#   - ANTHROPIC_API_KEY set in .env
#   - config.yaml configured
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load environment ──────────────────────────────────────────────────────────
if [[ -f .env ]]; then
    set -a; source .env; set +a
fi

LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/agent_run.log"
mkdir -p "$LOG_DIR"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"; }

# ── Parse args ────────────────────────────────────────────────────────────────
DRY_RUN=false
CHECK_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --dry-run)    DRY_RUN=true ;;
        --check)      CHECK_ONLY=true ;;
        *)            echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

# ── Check prerequisites ───────────────────────────────────────────────────────
if ! command -v claude &>/dev/null; then
    log "ERROR: 'claude' CLI not found."
    log "Install with: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# ANTHROPIC_API_KEY is only needed for the Python SDK (vps_generate.py).
# The claude CLI authenticates via OAuth (your subscription login) — no API key required here.
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    log "Note: ANTHROPIC_API_KEY is set (used by Python SDK scripts, not needed for claude CLI)"
fi

if [[ ! -f config.yaml ]]; then
    log "ERROR: config.yaml not found. Copy config.example.yaml and edit it."
    exit 1
fi

# ── Extract DB path from config ───────────────────────────────────────────────
DB_PATH=$(python3 -c "
import yaml, os
with open('config.yaml') as f:
    c = yaml.safe_load(f)
print(os.path.expanduser(c['vps']['db_path']))
" 2>/dev/null) || DB_PATH="$HOME/anki-agent/cards.db"

export DB_PATH
export PROJECT_DIR="$SCRIPT_DIR"
export TODAY=$(date -u +%Y-%m-%d)

if [[ "$CHECK_ONLY" == true ]]; then
    log "Check: claude CLI found at $(command -v claude)"
    log "Check: claude auth — $(claude -p 'respond with: authenticated' --max-turns 1 --allowedTools '' 2>/dev/null || echo 'NOT authenticated (run: claude auth login)')"
    log "Check: DB_PATH = $DB_PATH"
    log "Check: PROJECT_DIR = $PROJECT_DIR"
    TOPICS_ENABLED=$(python3 -c "
import yaml
from pathlib import Path
count = sum(
    1 for p in Path('topics').glob('*.yaml')
    if yaml.safe_load(p.read_text()).get('enabled', True)
)
print(count)
" 2>/dev/null || echo "?")
    log "Check: $TOPICS_ENABLED enabled topic(s) in topics/"
    log "All checks passed."
    exit 0
fi

# ── Build prompt (expand ${DB_PATH}, ${PROJECT_DIR}, ${TODAY}) ────────────────
PROMPT=$(envsubst < agent_instructions.md)

if [[ "$DRY_RUN" == true ]]; then
    echo "────────────────────────────────────────────────────────────"
    echo "DRY RUN — Agent prompt that would be sent to claude -p:"
    echo "────────────────────────────────────────────────────────────"
    echo "$PROMPT"
    exit 0
fi

# ── Quick auth + connectivity check ──────────────────────────────────────────
log "Checking claude auth..."
if ! timeout 30 claude -p "respond with: ok" --max-turns 1 --allowedTools "" > /dev/null 2>&1; then
    log "ERROR: claude is not responding. Check auth with: claude auth login"
    exit 1
fi
log "Claude auth OK."

# ── Run agent ─────────────────────────────────────────────────────────────────
log "Starting agent run (DB: $DB_PATH)"
log "Topics: $(python3 topics.py list 2>/dev/null | grep -c '✓' || echo '?') enabled"
log "────────────────────────────────────────────────────"

# Clean up previous output file so we can detect if agent produced new output
rm -f agent_output.json

# stdbuf -oL forces line-buffered output so each line appears immediately
# (without it, piping into tee causes block-buffering and nothing shows up live)
stdbuf -oL claude -p "$PROMPT" \
    --allowedTools "Bash,Read,Write,WebSearch,WebFetch" \
    --max-turns 50 \
    --verbose \
    2>&1 | stdbuf -oL tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

# ── Verify output ─────────────────────────────────────────────────────────────
if [[ $EXIT_CODE -ne 0 ]]; then
    log "ERROR: claude exited with code $EXIT_CODE"
    exit $EXIT_CODE
fi

if [[ -f agent_output.json ]]; then
    CARD_COUNT=$(python3 -c "import json; print(len(json.load(open('agent_output.json'))))" 2>/dev/null || echo "?")
    log "Agent produced $CARD_COUNT card(s) in agent_output.json"

    # Safety net: ingest if the agent somehow skipped step 5
    # (idempotent — will just add duplicates which AnkiConnect will reject)
    if ! grep -q '"ingested"' "$LOG_FILE" 2>/dev/null; then
        log "Agent did not call --ingest-json; running it now as fallback..."
        python3 vps_queue.py --db "$DB_PATH" --ingest-json agent_output.json | tee -a "$LOG_FILE"
    fi
else
    log "WARNING: agent_output.json was not created. Check the log for errors."
fi

STATS=$(python3 vps_queue.py --db "$DB_PATH" --stats 2>/dev/null || echo "{}")
log "Queue stats: $STATS"
log "Agent run complete."
