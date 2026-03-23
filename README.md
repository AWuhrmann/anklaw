# Anki Agent

An autonomous LLM-powered system that generates Anki flashcards daily on a VPS and syncs them to your local Anki installation — no AnkiWeb API required.

---

## Overview

Anki Agent runs two cron jobs:

1. **On your VPS** — a daily job calls an LLM (Claude or GPT-4) with your topic instructions, generates a batch of flashcards, and stores them in a local SQLite queue.
2. **On your local machine** — a periodic job SSHes into the VPS, reads pending cards from the queue, imports them into Anki via the AnkiConnect add-on, then marks them as imported on the VPS.

You never need an AnkiWeb API key. If you want cloud sync, AnkiConnect can trigger it after import.

---

## Architecture

```
┌─────────────────────────────────────┐       ┌──────────────────────────────────┐
│              VPS                    │       │         Local Machine            │
│                                     │  SSH  │                                  │
│  cron (daily) → vps_generate.py     │──────>│  cron (30min) → local_sync.py    │
│       │                             │       │       │                          │
│       v                             │       │       v                          │
│  LLM API (Anthropic/OpenAI)         │       │  AnkiConnect (localhost:8765)    │
│       │                             │       │  (Anki must be running)          │
│       v                             │       │                                  │
│  SQLite queue (cards.db)            │       │  cards.db on VPS updated         │
│  - pending                          │       │  (pending → imported)            │
│  - imported                         │       │                                  │
│  - failed                           │       └──────────────────────────────────┘
└─────────────────────────────────────┘
```

**Key design decisions:**

- **SQLite on the VPS** is the source of truth. The local machine is stateless.
- **SSH + `vps_queue.py`** is used for all queue operations from the local side — no open ports needed on the VPS beyond SSH.
- **AnkiConnect** (add-on ID: 2055492159) handles the actual Anki import on the local machine.
- **No AnkiWeb API** is needed. AnkiConnect can optionally trigger AnkiWeb sync after each import.
- **Offline tolerance**: if your local machine is offline for days, pending cards accumulate in the queue and are bulk-imported the next time the sync runs.

---

## Prerequisites

### VPS
- Python 3.10+
- SSH access (key-based)
- An LLM API key: [Anthropic](https://console.anthropic.com/) or [OpenAI](https://platform.openai.com/)

### Local machine
- Python 3.10+
- [Anki](https://apps.ankiweb.net/) (desktop)
- [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on (ID: `2055492159`)
  - Install via Anki: Tools → Add-ons → Get Add-ons → paste `2055492159`
- SSH key pair with access to the VPS

---

## Installation

### 1. Clone on both machines

```bash
git clone https://github.com/youruser/anki-agent.git ~/anki-agent
cd ~/anki-agent
```

### 2. Set up the VPS

```bash
bash scripts/setup_vps.sh
```

This will:
- Check Python version
- Create a virtual environment and install dependencies
- Copy `config.example.yaml` → `config.yaml` and `.env.example` → `.env`
- Print a suggested cron entry

Then edit your config:

```bash
nano config.yaml   # fill in topic_instructions, deck_name, llm_model
nano .env          # add ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Set up the local machine

```bash
bash scripts/setup_local.sh
```

This will:
- Create a virtual environment and install dependencies
- Copy `config.example.yaml` → `config.yaml`
- Test AnkiConnect (Anki must be running)
- Print a suggested cron entry

Then edit your config:

```bash
nano config.yaml   # fill in vps.host, vps.user, vps.ssh_key_path
```

---

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit it. The file is gitignored.

```yaml
vps:
  host: "1.2.3.4"              # Your VPS IP or hostname
  user: "ubuntu"               # SSH username
  ssh_key_path: "~/.ssh/id_rsa"
  db_path: "~/anki-agent/cards.db"
  script_path: "~/anki-agent"
  port: 22

local:
  anki_connect_url: "http://localhost:8765"

generation:
  cards_per_day: 20

  topic_instructions: |
    Generate flashcards about advanced Python programming.
    Focus on: async/await, decorators, metaclasses, memory management,
    and the standard library. Mix conceptual with practical questions.
    Assume an intermediate-to-advanced audience.

  deck_name: "Programming::Python"   # :: creates nested decks in Anki
  card_type: "Basic"                  # "Basic" or "Cloze"

  llm_provider: "anthropic"
  llm_model: "claude-opus-4-6"        # or "gpt-4o", "claude-sonnet-4-6"
  max_retries: 3
  research_enabled: false
```

**API keys** go in `.env` (never in `config.yaml`):

```
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

### Configuration options

| Field | Default | Description |
|---|---|---|
| `vps.host` | — | VPS IP or hostname (required) |
| `vps.user` | `ubuntu` | SSH username |
| `vps.ssh_key_path` | `~/.ssh/id_rsa` | Path to SSH private key |
| `vps.db_path` | `~/anki-agent/cards.db` | SQLite database path on VPS |
| `vps.script_path` | `~/anki-agent` | Project root on VPS |
| `vps.port` | `22` | SSH port |
| `local.anki_connect_url` | `http://localhost:8765` | AnkiConnect URL |
| `generation.cards_per_day` | `20` | Cards generated per cron run |
| `generation.topic_instructions` | — | Prompt describing what cards to generate |
| `generation.deck_name` | `AnkiAgent` | Target Anki deck (use `::` for sub-decks) |
| `generation.card_type` | `Basic` | `Basic` or `Cloze` |
| `generation.llm_provider` | `anthropic` | `anthropic` or `openai` |
| `generation.llm_model` | `claude-opus-4-6` | Model name |
| `generation.max_retries` | `3` | Retries on LLM parse failure |
| `generation.research_enabled` | `false` | Fetch web context before generating |

---

## CLI Reference

### VPS: `vps_generate.py`

Run daily on the VPS to generate and queue cards.

```bash
python vps_generate.py                    # Normal run
python vps_generate.py --dry-run          # Generate but do NOT save to queue
python vps_generate.py --mock-llm         # Use mock cards (no API call)
python vps_generate.py --test-connection  # Verify LLM API key and exit
python vps_generate.py --stats            # Show queue stats and exit
python vps_generate.py --n 10             # Override cards_per_day for this run
python vps_generate.py --config /path/to/config.yaml
```

### Local: `local_sync.py`

Run periodically on your local machine to import cards from the VPS into Anki.

```bash
python local_sync.py                   # Normal sync
python local_sync.py --dry-run         # Show what would be imported, don't import
python local_sync.py --mock-vps        # Use a local DB instead of SSH (for testing)
python local_sync.py --mock-anki       # Log imports instead of calling AnkiConnect
python local_sync.py --test-anki       # Test AnkiConnect and exit
python local_sync.py --test-vps        # Test VPS SSH connection and exit
python local_sync.py --stats           # Show VPS queue stats and exit
python local_sync.py --retry-failed    # Reset failed cards on VPS to pending
python local_sync.py --no-ankiweb-sync # Skip AnkiWeb sync after import
```

### `simulate.py`

End-to-end pipeline test using a temporary SQLite DB. No real API calls or Anki needed by default.

```bash
python simulate.py                              # Fully mocked
python simulate.py --use-real-llm               # Real LLM, mock Anki
python simulate.py --use-real-anki              # Mock LLM, real Anki
python simulate.py --use-real-llm --use-real-anki  # Full end-to-end
python simulate.py --n 3                        # Generate only 3 cards
```

### `vps_queue.py`

Low-level CLI for the SQLite queue. Normally called remotely by `local_sync.py` via SSH, but can be used directly for debugging.

```bash
python vps_queue.py --db cards.db --list-pending
python vps_queue.py --db cards.db --mark-imported 1,2,3
python vps_queue.py --db cards.db --mark-failed 4,5 --error "reason"
python vps_queue.py --db cards.db --retry-failed
python vps_queue.py --db cards.db --stats
```

### Makefile shortcuts

```bash
make install            # Create venv and install dependencies
make test               # Run all tests
make test-cov           # Run tests with coverage report
make simulate           # Run pipeline simulation (mocked)
make simulate-real-llm  # Run simulation with real LLM API
make simulate-full      # Run simulation with real LLM + real Anki
make dry-run-generate   # Dry-run card generation
make dry-run-sync       # Dry-run local sync against local DB
make health-check       # Test LLM, AnkiConnect, VPS SSH, and queue stats
make stats              # Show VPS queue stats
make retry-failed       # Retry failed cards
make lint               # Lint with flake8
make clean              # Remove __pycache__, .pytest_cache, etc.
```

---

## Testing & Simulation

### Run the test suite

```bash
make install   # first time only
make test
```

All tests are fully offline — no LLM calls, no Anki needed, no SSH.

```
tests/test_queue.py          — SQLite queue CRUD operations
tests/test_generator.py      — Card generation and JSON parsing
tests/test_anki_connect.py   — AnkiConnect HTTP client
tests/test_integration.py    — Full pipeline: generate → queue → import cycle
```

### Run a full simulation before going live

```bash
# Step 1: verify everything works with mocks (no external services)
python simulate.py --n 5

# Step 2: verify LLM API key and card quality
python simulate.py --n 5 --use-real-llm

# Step 3: verify Anki import (open Anki first)
python simulate.py --n 3 --use-real-llm --use-real-anki
```

---

## Cron Setup

### VPS cron

```bash
crontab -e
```

Add:

```cron
# Anki Agent — generate cards daily at 03:00
0 3 * * * cd /home/ubuntu/anki-agent && ./venv/bin/python vps_generate.py >> logs/vps_generate.log 2>&1
```

### Local machine cron

```bash
crontab -e
```

Add:

```cron
# Anki Agent — sync cards every 30 minutes
*/30 * * * * cd /home/youruser/anki-agent && ./venv/bin/python local_sync.py >> logs/local_sync.log 2>&1
```

**Note:** The local sync only runs when your machine is on and Anki is running. If Anki is closed, the sync exits cleanly and retries at the next interval. Cards accumulate safely on the VPS.

### Verify cron is working

After the first VPS cron run:

```bash
# On VPS:
tail -f logs/vps_generate.log

# On local machine:
python local_sync.py --stats
```

---

## Troubleshooting

### "Config file not found"

```bash
cp config.example.yaml config.yaml
# Then edit config.yaml with your settings
```

### LLM connection fails

```bash
python vps_generate.py --test-connection
```

- Check that `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) is set in `.env`
- Verify the model name in `config.yaml` is correct (e.g., `claude-opus-4-6`, `gpt-4o`)
- Make sure your API key has sufficient credits

### AnkiConnect not available

```bash
python local_sync.py --test-anki
```

- Open Anki on your local machine
- Confirm AnkiConnect add-on is installed (Tools → Add-ons)
- Check AnkiConnect is listening: `curl http://localhost:8765` should return a response
- If using a non-default port, update `local.anki_connect_url` in `config.yaml`

### VPS SSH fails

```bash
python local_sync.py --test-vps
```

- Verify `vps.host`, `vps.user`, and `vps.ssh_key_path` in `config.yaml`
- Test manually: `ssh -i ~/.ssh/id_rsa ubuntu@your-vps.example.com`
- Check that the SSH key is added to `~/.ssh/authorized_keys` on the VPS
- If using a non-standard port, set `vps.port` in `config.yaml`

### Cards are generated but not imported

```bash
# Check queue on VPS
python local_sync.py --stats

# Dry-run the local sync to see what would be imported
python local_sync.py --dry-run

# Retry any failed cards
python local_sync.py --retry-failed
```

### Cards are duplicated in Anki

AnkiConnect uses `allowDuplicate: false` by default, so true duplicates are silently skipped. If you see unexpected duplicates, check whether the same deck received cards from another source.

### The LLM returned fewer cards than requested

This can happen if the model truncates its response. The generator will retry automatically (up to `max_retries` times). If it keeps happening, reduce `cards_per_day` or switch to a model with a larger output context.

### Cron job runs but nothing happens

- Check log files: `tail -50 logs/vps_generate.log` and `tail -50 logs/local_sync.log`
- Ensure the venv Python is used: the cron command should use `./venv/bin/python`, not `python3`
- Make sure `.env` is present and readable by the cron user
- Test the exact cron command manually in your shell

---

## FAQ

**Do I need AnkiWeb?**

No. Anki Agent uses AnkiConnect (a local add-on) to import cards directly into your Anki database. If you also want AnkiWeb cloud sync, AnkiConnect can trigger it after each import (enabled by default, disable with `--no-ankiweb-sync`).

**Can I use OpenAI instead of Anthropic?**

Yes. Set `llm_provider: "openai"` and `llm_model: "gpt-4o"` (or similar) in `config.yaml`, and add `OPENAI_API_KEY` to `.env`.

**What if my local machine is offline for several days?**

Cards accumulate in the VPS queue. The next time the local sync runs, it will bulk-import all pending cards. The queue has no expiry — cards stay pending until imported or explicitly failed.

**Can I generate cards on topics that change daily?**

The current design uses a static `topic_instructions` prompt. For dynamic topics, you can either edit `config.yaml` manually, or extend `vps_generate.py` to pull the topic from an external source (a file, an API, etc.) before calling the generator.

**What card types are supported?**

- `Basic` — front/back question-and-answer cards
- `Cloze` — cloze deletion cards using `{{c1::...}}` syntax

Set `card_type` in `config.yaml`. All cards in a batch use the same type.

**How do I use nested Anki decks?**

Use `::` as the separator in `deck_name`, e.g. `Programming::Python::Async`. AnkiConnect will create the full hierarchy if it doesn't exist.

**Can I run the VPS generation manually?**

Yes:

```bash
cd ~/anki-agent
source venv/bin/activate
python vps_generate.py --n 10
```

**How do I back up the card database?**

The SQLite file at `vps.db_path` (default: `~/anki-agent/cards.db`) is the complete record of all generated and imported cards. Copy it anywhere to back it up:

```bash
cp ~/anki-agent/cards.db ~/backups/cards-$(date +%Y%m%d).db
```

**The simulation fails with "FAIL: expected N imported, got M"**

This usually means a card import returned an error. Run `simulate.py --use-real-anki` with Anki open and check the output for individual card failures.

**Can I add web research enrichment?**

Set `research_enabled: true` in `config.yaml` and install the optional dependency:

```bash
pip install duckduckgo-search
```

The researcher will fetch the top 5 DuckDuckGo results for your `topic_instructions` and include them as context in the LLM prompt.

---

## Project Structure

```
anki-agent/
├── core/
│   ├── models.py        — Card, Batch, CardStatus, CardType dataclasses
│   ├── config.py        — Config loading from YAML + .env
│   ├── queue.py         — SQLite queue (save, get_pending, mark_imported, etc.)
│   ├── generator.py     — LLM card generation (Anthropic + OpenAI)
│   ├── researcher.py    — Optional DuckDuckGo research context
│   ├── anki_connect.py  — AnkiConnect HTTP client
│   └── vps_client.py    — SSH client for remote queue operations
├── vps_generate.py      — VPS entry point (run by cron)
├── vps_queue.py         — VPS queue CLI (called via SSH by local_sync.py)
├── local_sync.py        — Local entry point (run by cron)
├── simulate.py          — End-to-end pipeline simulation
├── scripts/
│   ├── setup_vps.sh     — VPS one-time setup
│   └── setup_local.sh   — Local machine one-time setup
├── tests/
│   ├── conftest.py
│   ├── test_queue.py
│   ├── test_generator.py
│   ├── test_anki_connect.py
│   └── test_integration.py
├── config.example.yaml  — Config template (copy to config.yaml)
├── .env.example         — Secrets template (copy to .env)
├── requirements.txt
└── Makefile
```

---

## License

MIT
