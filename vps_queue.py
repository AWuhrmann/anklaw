#!/usr/bin/env python3
"""
VPS queue CLI — called remotely via SSH by the local sync script.
Do not run this manually unless debugging.

Usage (via SSH from local machine):
  python vps_queue.py --db /path/to/cards.db --list-pending
  python vps_queue.py --db /path/to/cards.db --mark-imported 1,2,3
  python vps_queue.py --db /path/to/cards.db --mark-failed 4,5 --error "anki_error"
  python vps_queue.py --db /path/to/cards.db --retry-failed
  python vps_queue.py --db /path/to/cards.db --stats
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.queue import CardQueue


def main():
    parser = argparse.ArgumentParser(description="VPS queue CLI for remote SSH access")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-pending",  action="store_true", help="Output pending cards as JSON")
    group.add_argument("--mark-imported", metavar="IDS",       help="Comma-separated card IDs to mark imported")
    group.add_argument("--mark-failed",   metavar="IDS",       help="Comma-separated card IDs to mark failed")
    group.add_argument("--retry-failed",  action="store_true", help="Reset all failed cards to pending")
    group.add_argument("--stats",         action="store_true", help="Output queue statistics as JSON")

    parser.add_argument("--error", default="", help="Error message (used with --mark-failed)")
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


if __name__ == "__main__":
    main()
