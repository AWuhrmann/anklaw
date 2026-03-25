#!/usr/bin/env python3
"""
Local entry point — run periodically via cron to import queued cards into Anki.

Usage:
  python local_sync.py                  # normal sync
  python local_sync.py --dry-run        # show what would be imported, don't import
  python local_sync.py --mock-vps       # use a local DB instead of SSH (for testing)
  python local_sync.py --mock-anki      # log imports instead of calling AnkiConnect
  python local_sync.py --test-anki      # test AnkiConnect and exit
  python local_sync.py --test-vps       # test VPS SSH connection and exit
  python local_sync.py --stats          # show VPS queue stats and exit
  python local_sync.py --retry-failed   # reset failed cards on VPS to pending
  python local_sync.py --no-ankiweb-sync  # skip AnkiWeb sync after import
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.anki_connect import AnkiConnect, AnkiConnectError
from core.config import load_config
from core.queue import CardQueue
from core.vps_client import VPSClient, VPSClientError


def setup_logging(log_file: str):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Import pending Anki cards from VPS queue.")
    parser.add_argument("--config",            default="config.yaml")
    parser.add_argument("--dry-run",           action="store_true", help="Show what would be imported")
    parser.add_argument("--mock-vps",          action="store_true", help="Use local DB (skip SSH)")
    parser.add_argument("--mock-anki",         action="store_true", help="Log imports (skip AnkiConnect)")
    parser.add_argument("--local-db",          help="DB path when using --mock-vps")
    parser.add_argument("--test-anki",         action="store_true", help="Test AnkiConnect and exit")
    parser.add_argument("--test-vps",          action="store_true", help="Test VPS SSH and exit")
    parser.add_argument("--stats",             action="store_true", help="Show VPS queue stats and exit")
    parser.add_argument("--retry-failed",      action="store_true", help="Retry failed cards on VPS")
    parser.add_argument("--no-ankiweb-sync",   action="store_true", help="Skip AnkiWeb sync after import")
    parser.add_argument("--log-file",          default="logs/local_sync.log")
    args = parser.parse_args()

    setup_logging(args.log_file)
    logger = logging.getLogger("local_sync")

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    anki = AnkiConnect(config.local.anki_connect_url)

    # --- Quick checks ---
    if args.test_anki:
        ok = anki.is_available()
        print("AnkiConnect OK" if ok else "AnkiConnect FAILED — is Anki running?")
        sys.exit(0 if ok else 1)

    if args.test_vps:
        vps = _make_vps_client(config)
        ok = vps.is_available()
        print("VPS SSH OK" if ok else "VPS SSH FAILED — check host, user, and key")
        sys.exit(0 if ok else 1)

    # --- Fetch cards ---
    # Local mode: vps.host is empty or "localhost" → read DB directly (no SSH)
    use_local = args.mock_vps or not config.vps.host or config.vps.host in ("localhost", "127.0.0.1")

    if use_local:
        db_path = args.local_db or config.vps.db_path
        local_queue = CardQueue(db_path)

        if args.stats:
            _print_stats(local_queue.stats())
            return
        if args.retry_failed:
            n = local_queue.retry_failed()
            print(f"Reset {n} failed cards to pending")
            return

        cards = local_queue.get_pending()
        logger.info(f"Loaded {len(cards)} cards from local DB: {db_path}")
    else:
        vps = _make_vps_client(config)
        try:
            with vps:
                if args.stats:
                    _print_stats(vps.get_stats())
                    return
                if args.retry_failed:
                    n = vps.retry_failed()
                    print(f"Reset {n} failed cards to pending")
                    return
                cards = vps.get_pending_cards()
        except VPSClientError as e:
            logger.error(f"VPS error: {e}")
            sys.exit(1)

    if not cards:
        logger.info("No pending cards.")
        print("No pending cards — nothing to import.")
        return

    logger.info(f"Found {len(cards)} pending cards")

    # --- Dry run ---
    if args.dry_run:
        print(f"\n[DRY RUN] Would import {len(cards)} cards:")
        for i, card in enumerate(cards[:5], 1):
            print(f"  {i}. [{card.deck_name}] {card.front[:70]}")
        if len(cards) > 5:
            print(f"  ... and {len(cards) - 5} more")
        return

    # --- Import ---
    if args.mock_anki:
        succeeded = [c.id for c in cards]
        failed = []
        for card in cards:
            logger.info(f"  [MOCK ANKI] Would import: {card.front[:60]!r}")
    else:
        if not anki.is_available():
            logger.error("AnkiConnect not available. Is Anki running?")
            sys.exit(1)
        succeeded, failed = anki.add_cards(cards)

    # --- Update queue ---
    if use_local:
        db_path = args.local_db or config.vps.db_path
        local_queue = CardQueue(db_path)
        local_queue.mark_imported(succeeded)
        if failed:
            local_queue.mark_failed(failed, "anki_import_failed")
    else:
        vps = _make_vps_client(config)
        try:
            with vps:
                vps.mark_imported(succeeded)
                if failed:
                    vps.mark_failed(failed, "anki_import_failed")
        except VPSClientError as e:
            logger.error(f"Failed to update VPS queue after import: {e}")
            # Don't exit — cards were already imported; queue will just have stale pending entries

    # --- AnkiWeb sync ---
    if not args.mock_anki and not args.no_ankiweb_sync:
        anki.sync()

    logger.info(f"Import complete. Succeeded: {len(succeeded)}, Failed: {len(failed)}")
    result = f"Imported {len(succeeded)} cards"
    if failed:
        result += f" | {len(failed)} failed (use --retry-failed to retry)"
    print(result)


def _make_vps_client(config) -> VPSClient:
    return VPSClient(
        host=config.vps.host,
        user=config.vps.user,
        ssh_key_path=config.vps.ssh_key_path,
        port=config.vps.port,
        script_path=config.vps.script_path,
        db_path=config.vps.db_path,
    )


def _print_stats(stats: dict):
    print("Queue stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
