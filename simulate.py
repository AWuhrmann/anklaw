#!/usr/bin/env python3
"""
End-to-end pipeline simulation — validates the full flow without real API calls or Anki.

Use this to confirm everything works before waiting 24h for the cron to run.

Usage:
  python simulate.py                           # full mock simulation
  python simulate.py --use-real-llm            # real LLM API call, mock Anki
  python simulate.py --use-real-anki           # mock LLM, real Anki (Anki must be open)
  python simulate.py --use-real-llm --use-real-anki   # full end-to-end with real services
  python simulate.py --n 3                     # generate only 3 cards (faster)
"""
import argparse
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.anki_connect import AnkiConnect
from core.config import load_config
from core.generator import CardGenerator
from core.queue import CardQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("simulate")

SEPARATOR = "=" * 60


def main():
    parser = argparse.ArgumentParser(description="End-to-end pipeline simulation")
    parser.add_argument("--config",          default="config.yaml")
    parser.add_argument("--use-real-llm",    action="store_true", help="Make real LLM API calls")
    parser.add_argument("--use-real-anki",   action="store_true", help="Use real AnkiConnect")
    parser.add_argument("--n",               type=int, default=5,  help="Number of cards to generate")
    args = parser.parse_args()

    print(SEPARATOR)
    print("ANKI AGENT — PIPELINE SIMULATION")
    mode = []
    if args.use_real_llm:   mode.append("real LLM")
    if args.use_real_anki:  mode.append("real Anki")
    if not mode:            mode.append("fully mocked")
    print(f"Mode: {', '.join(mode)}")
    print(SEPARATOR)

    config = load_config(args.config)

    if not args.use_real_llm:
        config.generation.llm_provider = "_mock"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/simulation.db"

        # -- Step 1: Generation ---------------------------------------------
        print(f"\n[1/4] Generating {args.n} cards...")
        config.generation.cards_per_day = args.n
        generator = CardGenerator(config.generation)
        batch, cards = generator.generate(n=args.n)

        print(f"  Generated {len(cards)} cards (batch: {batch.id[:8]})")
        for i, card in enumerate(cards[:3], 1):
            print(f"     Card {i}: {card.front[:65]}")
        if len(cards) > 3:
            print(f"     ... and {len(cards) - 3} more")

        # -- Step 2: Queue --------------------------------------------------
        print(f"\n[2/4] Saving to SQLite queue ({db_path})...")
        queue = CardQueue(db_path)
        queue.save_batch(batch, cards)
        stats = queue.stats()
        print(f"  Saved. Stats: {stats}")

        # -- Step 3: Read back (simulates what local sync does) -------------
        print(f"\n[3/4] Reading pending cards back from queue...")
        pending = queue.get_pending()
        assert len(pending) == len(cards), (
            f"FAIL: expected {len(cards)} pending, got {len(pending)}"
        )
        print(f"  Read {len(pending)} pending cards — IDs: {[c.id for c in pending]}")

        # -- Step 4: Import into Anki ---------------------------------------
        print(f"\n[4/4] Importing into Anki...")
        if args.use_real_anki:
            anki = AnkiConnect(config.local.anki_connect_url)
            if not anki.is_available():
                print("  AnkiConnect not available. Open Anki and try again.")
                sys.exit(1)
            succeeded, failed = anki.add_cards(pending)
        else:
            succeeded = [c.id for c in pending]
            failed = []
            for card in pending:
                print(f"  [MOCK] {card.front[:65]}")

        queue.mark_imported(succeeded)
        if failed:
            queue.mark_failed(failed)

        # -- Assertions -----------------------------------------------------
        final = queue.stats()
        assert final["pending"] == 0,   f"FAIL: {final['pending']} cards still pending"
        assert final["imported"] == len(cards), (
            f"FAIL: expected {len(cards)} imported, got {final['imported']}"
        )

        print(f"\n{SEPARATOR}")
        print(f"SIMULATION PASSED")
        print(f"  Cards generated : {len(cards)}")
        print(f"  Cards imported  : {len(succeeded)}")
        print(f"  Cards failed    : {len(failed)}")
        print(f"  Final queue     : {final}")
        print(SEPARATOR)


if __name__ == "__main__":
    main()
