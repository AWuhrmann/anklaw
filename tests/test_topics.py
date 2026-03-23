"""
Tests for the topics management system and the new queue/vps_queue additions.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import yaml

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Batch, Card, CardType
from core.queue import CardQueue


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def topics_dir(tmp_path):
    d = tmp_path / "topics"
    d.mkdir()
    return d


@pytest.fixture
def sample_topic(topics_dir):
    data = {
        "name": "AI Researchers",
        "slug": "ai_researchers",
        "enabled": True,
        "description": "Prominent AI researchers",
        "cards_per_run": 8,
        "deck": "Research::People",
        "card_type": "Basic",
        "tags_base": ["ai", "researchers"],
        "research_strategy": {
            "search_queries": ["AI researchers 2025"],
        },
        "card_format": "Generate cards about researchers.",
    }
    path = topics_dir / "ai_researchers.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True))
    return path


@pytest.fixture
def disabled_topic(topics_dir):
    data = {
        "name": "Old Topic",
        "slug": "old_topic",
        "enabled": False,
        "description": "Disabled",
        "cards_per_run": 5,
        "deck": "Research::Old",
    }
    path = topics_dir / "old_topic.yaml"
    path.write_text(yaml.dump(data))
    return path


@pytest.fixture
def populated_queue(temp_db):
    q = CardQueue(temp_db)
    batch = Batch(
        id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        topic_snapshot="test",
        cards_requested=3,
        cards_generated=3,
        llm_model="test",
    )
    cards = [
        Card(front=f"Q{i}", back=f"A{i}", deck_name="Test", card_type=CardType.BASIC)
        for i in range(3)
    ]
    q.save_batch(batch, cards)
    return q


# ── CardQueue.get_all_fronts ───────────────────────────────────────────────────

class TestGetAllFronts:
    def test_empty_db_returns_empty(self, temp_db):
        q = CardQueue(temp_db)
        assert q.get_all_fronts() == []

    def test_returns_all_fronts(self, populated_queue):
        fronts = populated_queue.get_all_fronts()
        assert len(fronts) == 3
        assert "Q0" in fronts
        assert "Q2" in fronts

    def test_respects_limit(self, temp_db):
        q = CardQueue(temp_db)
        batch = Batch(id=str(uuid4()), created_at=datetime.now(timezone.utc),
                      topic_snapshot="t", cards_requested=10, cards_generated=10, llm_model="m")
        cards = [Card(front=f"Q{i}", back=f"A{i}", deck_name="T", card_type=CardType.BASIC)
                 for i in range(10)]
        q.save_batch(batch, cards)
        assert len(q.get_all_fronts(limit=3)) == 3

    def test_includes_imported_cards(self, populated_queue):
        """Even imported cards should appear in fronts to prevent re-adding."""
        pending = populated_queue.get_pending()
        populated_queue.mark_imported([pending[0].id])
        fronts = populated_queue.get_all_fronts()
        assert "Q0" in fronts  # imported but should still block duplicates


# ── vps_queue.py --list-fronts ────────────────────────────────────────────────

class TestVpsQueueListFronts:
    def _run(self, args: list, db: str) -> dict:
        result = subprocess.run(
            [sys.executable, "vps_queue.py", "--db", db] + args,
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

    def test_list_fronts_empty(self, temp_db):
        r = self._run(["--list-fronts"], temp_db)
        assert r["returncode"] == 0
        assert json.loads(r["stdout"]) == []

    def test_list_fronts_returns_fronts(self, populated_queue, temp_db):
        r = self._run(["--list-fronts"], temp_db)
        assert r["returncode"] == 0
        fronts = json.loads(r["stdout"])
        assert isinstance(fronts, list)


# ── vps_queue.py --ingest-json ────────────────────────────────────────────────

class TestVpsQueueIngestJson:
    def _run(self, args: list) -> dict:
        result = subprocess.run(
            [sys.executable, "vps_queue.py"] + args,
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

    def test_ingest_basic_cards(self, tmp_path, temp_db):
        cards = [
            {"front": "Who is Geoffrey Hinton?", "back": "Godfather of Deep Learning.",
             "tags": ["ai", "hinton"], "deck": "Research::People", "topic": "ai_researchers"},
            {"front": "What is backpropagation?", "back": "Algorithm for training neural nets.",
             "tags": ["ml", "backprop"], "deck": "Research::Concepts", "topic": "ai_researchers"},
        ]
        json_file = tmp_path / "agent_output.json"
        json_file.write_text(json.dumps(cards))

        r = self._run(["--db", temp_db, "--ingest-json", str(json_file)])
        assert r["returncode"] == 0

        result = json.loads(r["stdout"])
        assert result["ingested"] == 2
        assert "batch_id" in result
        assert "ai_researchers" in result["topics"]

        # Verify cards are in the queue
        q = CardQueue(temp_db)
        assert q.stats()["pending"] == 2

    def test_ingest_empty_file(self, tmp_path, temp_db):
        json_file = tmp_path / "empty.json"
        json_file.write_text("[]")
        r = self._run(["--db", temp_db, "--ingest-json", str(json_file)])
        assert r["returncode"] == 0
        result = json.loads(r["stdout"])
        assert result["ingested"] == 0

    def test_ingest_missing_file(self, temp_db):
        r = self._run(["--db", temp_db, "--ingest-json", "/nonexistent/path.json"])
        assert r["returncode"] == 1

    def test_ingest_multiple_topics(self, tmp_path, temp_db):
        cards = [
            {"front": "Q1", "back": "A1", "tags": [], "deck": "D", "topic": "topic_a"},
            {"front": "Q2", "back": "A2", "tags": [], "deck": "D", "topic": "topic_b"},
            {"front": "Q3", "back": "A3", "tags": [], "deck": "D", "topic": "topic_a"},
        ]
        json_file = tmp_path / "cards.json"
        json_file.write_text(json.dumps(cards))
        r = self._run(["--db", temp_db, "--ingest-json", str(json_file)])
        result = json.loads(r["stdout"])
        assert result["ingested"] == 3
        assert set(result["topics"]) == {"topic_a", "topic_b"}

    def test_ingest_cards_have_correct_content(self, tmp_path, temp_db):
        cards = [
            {"front": "Specific question?", "back": "Specific answer.",
             "tags": ["tag1", "tag2"], "deck": "My::Deck", "topic": "test"},
        ]
        json_file = tmp_path / "cards.json"
        json_file.write_text(json.dumps(cards))
        self._run(["--db", temp_db, "--ingest-json", str(json_file)])

        q = CardQueue(temp_db)
        pending = q.get_pending()
        assert len(pending) == 1
        assert pending[0].front == "Specific question?"
        assert pending[0].back == "Specific answer."
        assert pending[0].tags == ["tag1", "tag2"]
        assert pending[0].deck_name == "My::Deck"


# ── Topics loading ────────────────────────────────────────────────────────────

class TestTopicLoading:
    def test_load_valid_topic(self, sample_topic):
        data = yaml.safe_load(sample_topic.read_text())
        assert data["name"] == "AI Researchers"
        assert data["slug"] == "ai_researchers"
        assert data["enabled"] is True
        assert data["cards_per_run"] == 8
        assert isinstance(data["research_strategy"]["search_queries"], list)

    def test_disabled_flag(self, disabled_topic):
        data = yaml.safe_load(disabled_topic.read_text())
        assert data["enabled"] is False

    def test_filter_enabled_topics(self, topics_dir, sample_topic, disabled_topic):
        all_files = list(topics_dir.glob("*.yaml"))
        enabled = [
            yaml.safe_load(p.read_text())
            for p in all_files
            if yaml.safe_load(p.read_text()).get("enabled", True)
        ]
        assert len(enabled) == 1
        assert enabled[0]["slug"] == "ai_researchers"


# ── Topics CLI (topics.py) ────────────────────────────────────────────────────

class TestTopicsCLI:
    def _run(self, args: list, topics_dir: Path = None) -> dict:
        env = {}
        if topics_dir:
            # Monkeypatch TOPICS_DIR by running from a temp dir with a topics/ subdir
            pass
        result = subprocess.run(
            [sys.executable, "topics.py"] + args,
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

    def test_list_shows_topics(self):
        r = self._run(["list"])
        assert r["returncode"] == 0
        # Should show the example topics in the real topics/ dir
        assert "SLUG" in r["stdout"] or "No topics found" in r["stdout"]

    def test_show_existing_topic(self):
        r = self._run(["show", "ai_researchers"])
        assert r["returncode"] == 0
        assert "ai_researchers" in r["stdout"]

    def test_show_missing_topic(self):
        r = self._run(["show", "nonexistent_slug_xyz"])
        assert r["returncode"] == 1
        assert "not found" in r["stderr"]

    def test_enable_disable_cycle(self, tmp_path):
        """Enable then disable a topic and verify the YAML changes."""
        # Use the real topics dir (ai_researchers) but restore after
        topic_path = Path(__file__).parent.parent / "topics" / "ai_researchers.yaml"
        original = topic_path.read_text()

        try:
            r = self._run(["disable", "ai_researchers"])
            assert r["returncode"] == 0
            data = yaml.safe_load(topic_path.read_text())
            assert data["enabled"] is False

            r = self._run(["enable", "ai_researchers"])
            assert r["returncode"] == 0
            data = yaml.safe_load(topic_path.read_text())
            assert data["enabled"] is True
        finally:
            topic_path.write_text(original)
