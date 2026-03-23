import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import Batch, Card, CardStatus, CardType

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    topic_snapshot TEXT,
    cards_requested INTEGER,
    cards_generated INTEGER,
    llm_model   TEXT,
    status      TEXT DEFAULT 'completed'
);

CREATE TABLE IF NOT EXISTS cards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      TEXT REFERENCES batches(id),
    created_at    TEXT NOT NULL,
    front         TEXT NOT NULL,
    back          TEXT NOT NULL,
    tags          TEXT DEFAULT '[]',
    deck_name     TEXT NOT NULL,
    card_type     TEXT DEFAULT 'Basic',
    status        TEXT DEFAULT 'pending',
    imported_at   TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
CREATE INDEX IF NOT EXISTS idx_cards_batch  ON cards(batch_id);
"""


class CardQueue:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_batch(self, batch: Batch, cards: List[Card]):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO batches VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    batch.id,
                    batch.created_at.isoformat(),
                    batch.topic_snapshot,
                    batch.cards_requested,
                    batch.cards_generated,
                    batch.llm_model,
                    batch.status,
                ),
            )
            for card in cards:
                conn.execute(
                    "INSERT INTO cards "
                    "(batch_id, created_at, front, back, tags, deck_name, card_type, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        batch.id,
                        datetime.now(timezone.utc).isoformat(),
                        card.front,
                        card.back,
                        json.dumps(card.tags),
                        card.deck_name,
                        card.card_type.value,
                        CardStatus.PENDING.value,
                    ),
                )
        logger.info(f"Saved batch {batch.id[:8]} with {len(cards)} cards")

    def get_pending(self, limit: int = 200) -> List[Card]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM cards WHERE status = ? ORDER BY created_at ASC LIMIT ?",
                (CardStatus.PENDING.value, limit),
            ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def mark_imported(self, card_ids: List[int]):
        if not card_ids:
            return
        placeholders = ",".join("?" * len(card_ids))
        with self._conn() as conn:
            conn.execute(
                f"UPDATE cards SET status = ?, imported_at = ? WHERE id IN ({placeholders})",
                [CardStatus.IMPORTED.value, datetime.now(timezone.utc).isoformat()] + card_ids,
            )
        logger.info(f"Marked {len(card_ids)} cards as imported")

    def mark_failed(self, card_ids: List[int], error: str = ""):
        if not card_ids:
            return
        placeholders = ",".join("?" * len(card_ids))
        with self._conn() as conn:
            conn.execute(
                f"UPDATE cards SET status = ?, error_message = ? WHERE id IN ({placeholders})",
                [CardStatus.FAILED.value, error] + card_ids,
            )
        logger.warning(f"Marked {len(card_ids)} cards as failed: {error}")

    def retry_failed(self) -> int:
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE cards SET status = ?, error_message = NULL WHERE status = ?",
                (CardStatus.PENDING.value, CardStatus.FAILED.value),
            )
        count = result.rowcount
        logger.info(f"Reset {count} failed cards to pending")
        return count

    def stats(self) -> dict:
        with self._conn() as conn:
            total    = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
            pending  = conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'pending'").fetchone()[0]
            imported = conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'imported'").fetchone()[0]
            failed   = conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'failed'").fetchone()[0]
            batches  = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
            last_row = conn.execute(
                "SELECT created_at FROM batches ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return {
            "total": total,
            "pending": pending,
            "imported": imported,
            "failed": failed,
            "batches": batches,
            "last_batch_at": last_row[0] if last_row else None,
        }

    def get_all_fronts(self, limit: int = 500) -> list:
        """Return existing card front texts for deduplication. Most recent first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT front FROM cards ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row["front"] for row in rows]

    def _row_to_card(self, row: sqlite3.Row) -> Card:
        return Card(
            id=row["id"],
            batch_id=row["batch_id"],
            front=row["front"],
            back=row["back"],
            tags=json.loads(row["tags"]),
            deck_name=row["deck_name"],
            card_type=CardType(row["card_type"]),
            status=CardStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            imported_at=datetime.fromisoformat(row["imported_at"]) if row["imported_at"] else None,
        )
