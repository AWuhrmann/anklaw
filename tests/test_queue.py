import pytest
from datetime import datetime, timezone
from uuid import uuid4

from core.models import Batch, Card, CardStatus, CardType
from core.queue import CardQueue


def _batch(n: int = 3) -> Batch:
    return Batch(
        id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        topic_snapshot="Test topic",
        cards_requested=n,
        cards_generated=n,
        llm_model="test-model",
    )


def _cards(n: int = 3, deck: str = "Test") -> list:
    return [
        Card(front=f"Q{i}", back=f"A{i}", tags=["test"], deck_name=deck, card_type=CardType.BASIC)
        for i in range(n)
    ]


class TestCardQueue:
    def test_init_creates_tables(self, temp_db):
        q = CardQueue(temp_db)
        stats = q.stats()
        assert stats["total"] == 0
        assert stats["pending"] == 0

    def test_save_batch(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(3), _cards(3))
        stats = q.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 3
        assert stats["batches"] == 1

    def test_get_pending_returns_all(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(4), _cards(4))
        pending = q.get_pending()
        assert len(pending) == 4
        assert all(c.status == CardStatus.PENDING for c in pending)
        assert all(c.id is not None for c in pending)

    def test_get_pending_respects_limit(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(20), _cards(20))
        assert len(q.get_pending(limit=5)) == 5

    def test_pending_ordered_chronologically(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(5), _cards(5))
        pending = q.get_pending()
        ids = [c.id for c in pending]
        assert ids == sorted(ids)

    def test_mark_imported(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(3), _cards(3))
        pending = q.get_pending()
        q.mark_imported([c.id for c in pending[:2]])
        stats = q.stats()
        assert stats["imported"] == 2
        assert stats["pending"] == 1

    def test_mark_failed(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(2), _cards(2))
        pending = q.get_pending()
        q.mark_failed([pending[0].id], "test error")
        stats = q.stats()
        assert stats["failed"] == 1
        assert stats["pending"] == 1

    def test_retry_failed_resets_to_pending(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(3), _cards(3))
        pending = q.get_pending()
        q.mark_failed([c.id for c in pending])
        assert q.stats()["failed"] == 3
        count = q.retry_failed()
        assert count == 3
        assert q.stats()["failed"] == 0
        assert q.stats()["pending"] == 3

    def test_multiple_batches_accumulate(self, temp_db):
        q = CardQueue(temp_db)
        for _ in range(3):
            q.save_batch(_batch(5), _cards(5))
        stats = q.stats()
        assert stats["total"] == 15
        assert stats["batches"] == 3

    def test_last_batch_at_populated(self, temp_db):
        q = CardQueue(temp_db)
        q.save_batch(_batch(1), _cards(1))
        assert q.stats()["last_batch_at"] is not None

    def test_card_roundtrip(self, temp_db):
        """Cards stored and retrieved should have the same data."""
        q = CardQueue(temp_db)
        original = _cards(1)[0]
        original.tags = ["foo", "bar"]
        q.save_batch(_batch(1), [original])
        retrieved = q.get_pending()[0]
        assert retrieved.front == original.front
        assert retrieved.back == original.back
        assert retrieved.tags == original.tags
        assert retrieved.deck_name == original.deck_name
