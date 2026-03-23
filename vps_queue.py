#!/usr/bin/env python3
"""
VPS queue CLI — called remotely via SSH by the local sync script,
and by the Claude Code agent during its daily run.

Usage (via SSH from local machine):
  python vps_queue.py --db /path/to/cards.db --list-pending
  python vps_queue.py --db /path/to/cards.db --mark-imported 1,2,3
  python vps_queue.py --db /path/to/cards.db --mark-failed 4,5 --error "anki_error"
  python vps_queue.py --db /path/to/cards.db --retry-failed
  python vps_queue.py --db /path/to/cards.db --stats

Usage (by the Claude Code agent on VPS):
  python vps_queue.py --db /path/to/cards.db --list-fronts
  python vps_queue.py --db /path/to/cards.db --ingest-json agent_output.json
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.models import Batch, Card, CardType
from core.queue import CardQueue


def main():
    parser = argparse.ArgumentParser(description="VPS queue CLI for remote SSH access and agent use")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-pending",  action="store_true", help="Output pending cards as JSON")
    group.add_argument("--list-fronts",   action="store_true", help="Output all card fronts as JSON (for agent deduplication)")
    group.add_argument("--mark-imported", metavar="IDS",       help="Comma-separated card IDs to mark imported")
    group.add_argument("--mark-failed",   metavar="IDS",       help="Comma-separated card IDs to mark failed")
    group.add_argument("--retry-failed",  action="store_true", help="Reset all failed cards to pending")
    group.add_argument("--stats",         action="store_true", help="Output queue statistics as JSON")
    group.add_argument("--ingest-json",   metavar="FILE",      help="Ingest cards from agent output JSON file")

    parser.add_argument("--error",        default="",          help="Error message (used with --mark-failed)")
    parser.add_argument("--limit",        type=int, default=500, help="Limit for --list-fronts (default 500)")
    args = parser.parse_args()

    queue = CardQueue(args.db)

    if args.list_pending:
        cards = queue.get_pending()
        print(json.dumps([
            {
                "id":        c.id,
                "front":     c.front,
                "back":      c.back,
                "tags":      c.tags,
                "deck_name": c.deck_name,
                "card_type": c.card_type.value,
                "batch_id":  c.batch_id,
                "status":    c.status.value,
            }
            for c in cards
        ]))

    elif args.mark_imported:
        ids = list(map(int, args.mark_imported.split(",")))
        queue.mark_imported(ids)
        print(json.dumps({"marked_imported": len(ids)}))

    elif args.mark_failed:
        ids = list(map(int, args.mark_failed.split(",")))
        queue.mark_failed(ids, args.error)
        print(json.dumps({"marked_failed": len(ids)}))

    elif args.retry_failed:
        count = queue.retry_failed()
        print(json.dumps({"reset": count}))

    elif args.stats:
        print(json.dumps(queue.stats()))

    elif args.list_fronts:
        fronts = queue.get_all_fronts(limit=args.limit)
        print(json.dumps(fronts))

    elif args.ingest_json:
        path = Path(args.ingest_json)
        if not path.exists():
            print(json.dumps({"error": f"File not found: {args.ingest_json}"}), file=sys.stderr)
            sys.exit(1)

        with open(path) as f:
            cards_data = json.load(f)

        if not cards_data:
            print(json.dumps({"ingested": 0, "note": "empty input"}))
            return

        topics = sorted({item.get("topic", "agent_run") for item in cards_data})
        cards = [
            Card(
                front=item["front"].strip(),
                back=item["back"].strip(),
                tags=item.get("tags", []),
                deck_name=item.get("deck", "AnkiAgent::Research"),
                card_type=CardType(item.get("card_type", "Basic")),
            )
            for item in cards_data
        ]
        batch = Batch(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            topic_snapshot=", ".join(topics),
            cards_requested=len(cards),
            cards_generated=len(cards),
            llm_model="claude-code-agent",
        )
        queue.save_batch(batch, cards)
        print(json.dumps({"ingested": len(cards), "batch_id": batch.id, "topics": topics}))


if __name__ == "__main__":
    main()
