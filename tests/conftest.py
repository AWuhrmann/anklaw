import pytest
from pathlib import Path


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def config_file(tmp_path):
    content = """\
vps:
  host: "test.example.com"
  user: "ubuntu"
  ssh_key_path: "~/.ssh/id_rsa"
  db_path: "/home/ubuntu/anki-agent/cards.db"
  script_path: "/home/ubuntu/anki-agent"
  port: 22
local:
  anki_connect_url: "http://localhost:8765"
generation:
  cards_per_day: 5
  topic_instructions: "Generate flashcards about Python."
  deck_name: "Test::AnkiAgent"
  card_type: "Basic"
  llm_provider: "anthropic"
  llm_model: "claude-opus-4-6"
  max_retries: 2
"""
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return str(path)


@pytest.fixture
def sample_cards():
    from core.models import Card, CardType
    return [
        Card(
            front="What is Python?",
            back="A high-level, interpreted programming language.",
            tags=["python", "programming"],
            deck_name="Test",
            card_type=CardType.BASIC,
        ),
        Card(
            front="What is a Python list?",
            back="An ordered, mutable sequence of elements.",
            tags=["python", "data-structures"],
            deck_name="Test",
            card_type=CardType.BASIC,
        ),
    ]
