"""
Integration tests: full pipeline with all external dependencies mocked.
No network calls, no Anki needed.
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from core.config import GenerationConfig
from core.generator import CardGenerator
from core.models import Batch, Card, CardStatus, CardType
from core.queue import CardQueue


def _batch(n: int = 5) -> Batch:
    return Batch(
        id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        topic_snapshot="Integration test topic",
        cards_requested=n,
        cards_generated=n,
        llm_model="mock",
    )


def _cards(n: int = 5) -> list:
    return [
        Card(front=f"Q{i}", back=f"A{i}", tags=["integration"], deck_name="Test::Integration",
             card_type=CardType.BASIC)
        for i in range(n)
    ]


class TestFullPipeline:
    def test_generate_queue_import_cycle(self, tmp_path):
        """A complete day: VPS generates -> queues -> local imports."""
        db = str(tmp_path / "cards.db")
        cfg = GenerationConfig(
            cards_per_day=5, topic_instructions="test", deck_name="Test",
            card_type="Basic", llm_provider="_mock", llm_model="mock",
        )
        gen = CardGenerator(cfg)
        batch, cards = gen.generate(n=5)
        assert len(cards) == 5

        queue = CardQueue(db)
        queue.save_batch(batch, cards)
        assert queue.stats()["pending"] == 5

        pending = queue.get_pending()
        assert len(pending) == 5

        queue.mark_imported([c.id for c in pending])
        final = queue.stats()
        assert final["pending"] == 0
        assert final["imported"] == 5

    def test_partial_failure_then_retry(self, tmp_path):
        """3 cards succeed, 1 fails, retry -> eventual full import."""
        db = str(tmp_path / "cards.db")
        queue = CardQueue(db)
        queue.save_batch(_batch(4), _cards(4))

        pending = queue.get_pending()
        queue.mark_imported([c.id for c in pending[:3]])
        queue.mark_failed([pending[3].id], "anki_error")

        s = queue.stats()
        assert s["imported"] == 3
        assert s["failed"] == 1
        assert s["pending"] == 0

        # Retry
        queue.retry_failed()
        assert queue.stats()["pending"] == 1
        assert queue.stats()["failed"] == 0

        retried = queue.get_pending()
        queue.mark_imported([retried[0].id])

        final = queue.stats()
        assert final["pending"] == 0
        assert final["failed"] == 0
        assert final["imported"] == 4

    def test_multi_day_accumulation(self, tmp_path):
        """Machine offline for 3 days -> bulk import on day 4."""
        db = str(tmp_path / "cards.db")
        cfg = GenerationConfig(
            cards_per_day=10, topic_instructions="test", deck_name="Test",
            card_type="Basic", llm_provider="_mock", llm_model="mock",
        )
        gen = CardGenerator(cfg)
        queue = CardQueue(db)

        for _ in range(3):
            batch, cards = gen.generate(n=10)
            queue.save_batch(batch, cards)

        assert queue.stats()["pending"] == 30
        assert queue.stats()["batches"] == 3

        all_pending = queue.get_pending()
        assert len(all_pending) == 30
        queue.mark_imported([c.id for c in all_pending])
        assert queue.stats()["pending"] == 0
        assert queue.stats()["imported"] == 30

    def test_config_loading(self, config_file):
        from core.config import load_config
        config = load_config(config_file)
        assert config.vps.host == "test.example.com"
        assert config.generation.cards_per_day == 5
        assert config.generation.deck_name == "Test::AnkiAgent"
        assert config.local.anki_connect_url == "http://localhost:8765"

    def test_config_missing_file_raises(self, tmp_path):
        from core.config import load_config
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config(str(tmp_path / "nonexistent.yaml"))
