# anki-agent

A Claude Code agent that runs daily, researches your topics on the web, and adds Anki flashcards to a queue — which your local machine imports automatically.

## How it works

```
run_agent.sh (daily cron)
  └─ claude -p [agent_instructions.md]
       ├─ reads topics/ directory
       ├─ checks existing cards (deduplication)
       ├─ searches the web (WebSearch tool)
       └─ writes cards → SQLite queue

local_sync.py (periodic cron, Anki must be open)
  └─ reads pending cards from queue
       └─ imports into Anki via AnkiConnect
```

Two setups are supported:

| | Single machine | Two machines |
|---|---|---|
| Agent runs on | Your computer | VPS |
| Anki runs on | Your computer | Your computer |
| Sync method | Local DB | SSH |
| `vps.host` in config | *(empty)* | VPS IP/hostname |

---

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://github.com/anthropics/claude-code) — `npm install -g @anthropic-ai/claude-code` + `claude auth login`
- [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed in Anki (ID: `2055492159`)

---

## Installation

```bash
git clone https://github.com/yourname/anki-agent
cd anki-agent
make install
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
- **Single machine**: leave `vps.host` empty, set `db_path` to wherever you want the database
- **Two machines**: set `vps.host`, `vps.user`, `vps.ssh_key_path`, `vps.script_path` (path to this repo on the VPS)

---

## Topics

Topics are YAML files in `topics/` that tell the agent what to research and how to structure the cards.

```bash
python topics.py list                  # see all topics
python topics.py add                   # interactive wizard
python topics.py enable <slug>
python topics.py disable <slug>
python topics.py show <slug>           # inspect full config
```

Two example topics are included: `ai_researchers` and `trending_papers`. Edit them or add your own.

---

## Running

### Generate cards (on the machine where the agent runs)

```bash
bash run_agent.sh --check      # verify auth and config
bash run_agent.sh --dry-run    # print the agent prompt
bash run_agent.sh              # run for real
```

### Import into Anki (on the machine where Anki runs, with Anki open)

```bash
python local_sync.py --test-anki   # verify AnkiConnect
python local_sync.py --dry-run     # preview cards
python local_sync.py               # import
```

---

## Cron setup

**On the agent machine** (`crontab -e`):
```
0 3 * * *  cd ~/anki-agent && bash run_agent.sh >> logs/agent_run.log 2>&1
```

**On the local machine** (skip if single-machine setup, cron handles both):
```
*/30 * * * *  cd ~/anki-agent && ./venv/bin/python local_sync.py >> logs/local_sync.log 2>&1
```

---

## Testing without cron

```bash
make simulate              # full pipeline, no real APIs
make simulate-real-llm     # real LLM, mock Anki
make test                  # unit + integration tests
```

---

## Queue management

```bash
python local_sync.py --stats           # pending / imported / failed counts
python local_sync.py --retry-failed    # re-queue failed cards
```

---

## Alternative: direct API mode

If you don't want to use Claude Code, `vps_generate.py` calls the LLM API directly (no web search, no topics system). Add your API key to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
python vps_generate.py --dry-run
python vps_generate.py
```

---

## Project structure

```
run_agent.sh          # daily agent runner (Claude Code)
local_sync.py         # imports pending cards into Anki
vps_generate.py       # alternative: direct API mode
vps_queue.py          # queue CLI (called via SSH or locally)
simulate.py           # end-to-end pipeline test
topics.py             # topic management CLI
topics/               # research topic definitions (YAML)
core/                 # library: queue, generator, AnkiConnect, SSH client
tests/                # pytest suite (55 tests)
```
