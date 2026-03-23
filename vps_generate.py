#!/usr/bin/env python3
"""
VPS entry point — run daily via cron to generate new Anki cards.

Usage:
  python vps_generate.py                   # normal run
  python vps_generate.py --dry-run         # generate but do NOT save
  python vps_generate.py --mock-llm        # use mock cards (no API call)
  python vps_generate.py --test-connection # verify LLM API key and exit
  python vps_generate.py --n 10            # override card count
  python vps_generate.py --stats           # show queue stats and exit
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import load_config
from core.generator import CardGenerator
from core.queue import CardQueue
from core.researcher import Researcher


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
    parser = argparse.ArgumentParser(description="Generate Anki cards via LLM and queue them.")
    parser.add_argument("--config",          default="config.yaml")
    parser.add_argument("--dry-run",         action="store_true", help="Generate but don't save to queue")
    parser.add_argument("--mock-llm",        action="store_true", help="Use mock cards (no API call)")
    parser.add_argument("--test-connection", action="store_true", help="Test LLM connection and exit")
    parser.add_argument("--stats",           action="store_true", help="Show queue stats and exit")
    parser.add_argument("--n",               type=int,            help="Override cards_per_day")
    parser.add_argument("--log-file",        default="logs/vps_generate.log")
    args = parser.parse_args()

    setup_logging(args.log_file)
    logger = logging.getLogger("vps_generate")

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.mock_llm:
        config.generation.llm_provider = "_mock"

    queue = CardQueue(config.vps.db_path)

    if args.stats:
        stats = queue.stats()
        print(f"Queue stats:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    generator = CardGenerator(config.generation)

    if args.test_connection:
        ok = generator.test_connection()
        if ok:
            print("LLM connection OK")
        else:
            print("LLM connection FAILED — check your API key and model name")
            sys.exit(1)
        return

    # Optional research context
    research_ctx = ""
    if config.generation.research_enabled:
        researcher = Researcher(enabled=True)
        logger.info("Fetching research context...")
        research_ctx = researcher.get_context(config.generation.topic_instructions)

    n = args.n or config.generation.cards_per_day
    logger.info(f"Generating {n} cards (provider: {config.generation.llm_provider}, model: {config.generation.llm_model})")

    try:
        batch, cards = generator.generate(
            n=n,
            research_context=research_ctx,
            dry_run=args.dry_run,
        )
    except RuntimeError as e:
        logger.error(f"Card generation failed: {e}")
        sys.exit(1)

    if args.dry_run:
        print(f"\n[DRY RUN] Would save {len(cards)} cards to queue. Preview:")
        for i, card in enumerate(cards[:5], 1):
            print(f"  {i}. Q: {card.front[:80]}")
            print(f"     A: {card.back[:60]}")
        if len(cards) > 5:
            print(f"  ... and {len(cards) - 5} more")
        return

    queue.save_batch(batch, cards)
    stats = queue.stats()
    logger.info(f"Done. Queue: {stats['pending']} pending, {stats['imported']} imported total")
    print(f"Added {len(cards)} cards (batch {batch.id[:8]}). Queue: {stats['pending']} pending.")


if __name__ == "__main__":
    main()
