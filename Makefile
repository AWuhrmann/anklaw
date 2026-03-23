.PHONY: install test simulate dry-run-generate dry-run-sync health-check lint clean

PYTHON := python3
VENV   := venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python

# -- Setup --------------------------------------------------------------------

install: $(VENV)/bin/activate

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "Install complete."
	@echo "  Next: cp config.example.yaml config.yaml && cp .env.example .env"
	@echo "  Then edit both files with your settings."

# -- Testing & Simulation -----------------------------------------------------

test:
	$(PY) -m pytest tests/ -v --tb=short

test-cov:
	$(PY) -m pytest tests/ -v --cov=core --cov-report=term-missing

simulate:
	$(PY) simulate.py --n 5

simulate-real-llm:
	$(PY) simulate.py --n 5 --use-real-llm

simulate-full:
	$(PY) simulate.py --n 5 --use-real-llm --use-real-anki

# -- Individual component tests -----------------------------------------------

dry-run-generate:
	$(PY) vps_generate.py --dry-run --n 5

dry-run-sync:
	$(PY) local_sync.py --dry-run --mock-vps --local-db cards.db

test-llm-connection:
	$(PY) vps_generate.py --test-connection

test-anki-connection:
	$(PY) local_sync.py --test-anki

test-vps-connection:
	$(PY) local_sync.py --test-vps

# -- Health check -------------------------------------------------------------

health-check:
	@echo "-- LLM connection ------------------"
	-$(PY) vps_generate.py --test-connection
	@echo "-- AnkiConnect ---------------------"
	-$(PY) local_sync.py --test-anki
	@echo "-- VPS SSH -------------------------"
	-$(PY) local_sync.py --test-vps
	@echo "-- Queue stats (VPS) ---------------"
	-$(PY) local_sync.py --stats

# -- Queue management ---------------------------------------------------------

stats:
	$(PY) local_sync.py --stats

retry-failed:
	$(PY) local_sync.py --retry-failed

# -- Utilities ----------------------------------------------------------------

lint:
	$(PY) -m flake8 core/ vps_generate.py local_sync.py simulate.py vps_queue.py --max-line-length 100

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache/ *.egg-info/
