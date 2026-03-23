#!/usr/bin/env python3
"""
Manage Anki agent research topics.

Topics are YAML files in the topics/ directory. Each topic tells the agent
what to research, how to structure the cards, and how many to generate per run.

Usage:
  python topics.py list                    # List all topics with status
  python topics.py show <slug>             # Show full topic config
  python topics.py enable <slug>           # Enable a topic
  python topics.py disable <slug>          # Disable a topic
  python topics.py add                     # Add a new topic (interactive wizard)
  python topics.py remove <slug>           # Remove a topic (prompts for confirmation)
  python topics.py edit <slug>             # Open topic file in $EDITOR
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import yaml

TOPICS_DIR = Path(__file__).parent / "topics"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_topic(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _save_topic(path: Path, data: dict):
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _all_topic_files() -> list:
    TOPICS_DIR.mkdir(exist_ok=True)
    return sorted(TOPICS_DIR.glob("*.yaml"))


def _find_topic(slug: str) -> Optional[Path]:
    path = TOPICS_DIR / f"{slug}.yaml"
    if path.exists():
        return path
    # Also try matching by name or partial slug
    for p in _all_topic_files():
        data = _load_topic(p)
        if data.get("slug") == slug or data.get("name", "").lower() == slug.lower():
            return p
    return None


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_list(args):
    files = _all_topic_files()
    if not files:
        print("No topics found. Run: python topics.py add")
        return

    print(f"{'SLUG':<28} {'STATUS':<10} {'CARDS/RUN':<10} NAME")
    print("─" * 70)
    for path in files:
        data = _load_topic(path)
        slug    = data.get("slug", path.stem)
        name    = data.get("name", slug)
        enabled = data.get("enabled", True)
        n       = data.get("cards_per_run", "?")
        status  = "enabled" if enabled else "disabled"
        marker  = "✓" if enabled else "✗"
        print(f"{marker} {slug:<26} {status:<10} {str(n):<10} {name}")


def cmd_show(args):
    path = _find_topic(args.slug)
    if not path:
        print(f"Topic not found: {args.slug!r}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        print(f.read())


def cmd_enable(args):
    path = _find_topic(args.slug)
    if not path:
        print(f"Topic not found: {args.slug!r}", file=sys.stderr)
        sys.exit(1)
    data = _load_topic(path)
    data["enabled"] = True
    _save_topic(path, data)
    print(f"Enabled: {data.get('name', args.slug)}")


def cmd_disable(args):
    path = _find_topic(args.slug)
    if not path:
        print(f"Topic not found: {args.slug!r}", file=sys.stderr)
        sys.exit(1)
    data = _load_topic(path)
    data["enabled"] = False
    _save_topic(path, data)
    print(f"Disabled: {data.get('name', args.slug)}")


def cmd_remove(args):
    path = _find_topic(args.slug)
    if not path:
        print(f"Topic not found: {args.slug!r}", file=sys.stderr)
        sys.exit(1)
    data = _load_topic(path)
    name = data.get("name", args.slug)
    answer = input(f"Remove topic '{name}'? This cannot be undone. [y/N] ").strip().lower()
    if answer == "y":
        path.unlink()
        print(f"Removed: {name}")
    else:
        print("Cancelled.")


def cmd_edit(args):
    path = _find_topic(args.slug)
    if not path:
        print(f"Topic not found: {args.slug!r}", file=sys.stderr)
        sys.exit(1)
    editor = os.environ.get("EDITOR", "nano")
    os.execvp(editor, [editor, str(path)])


def cmd_add(args):
    print("Add a new research topic")
    print("─" * 40)

    name = input("Topic name (display name): ").strip()
    if not name:
        print("Name is required.", file=sys.stderr)
        sys.exit(1)

    default_slug = _slugify(name)
    slug = input(f"Slug [{default_slug}]: ").strip() or default_slug

    # Check for conflicts
    if (TOPICS_DIR / f"{slug}.yaml").exists():
        print(f"Topic '{slug}' already exists. Edit it with: python topics.py edit {slug}")
        sys.exit(1)

    description = input("Description (one line): ").strip()

    default_n = "10"
    n_str = input(f"Cards per run [{default_n}]: ").strip() or default_n
    try:
        cards_per_run = int(n_str)
    except ValueError:
        cards_per_run = 10

    deck_default = f"Research::{name.replace(' ', '')}"
    deck = input(f"Anki deck name [{deck_default}]: ").strip() or deck_default

    print("\nSearch queries (one per line, empty line to finish):")
    queries = []
    while True:
        q = input("  > ").strip()
        if not q:
            break
        queries.append(q)
    if not queries:
        queries = [f"{name} latest 2025", f"{name} research recent"]

    print("\nCard format instructions (describe structure, Ctrl+D when done):")
    print("  Example: 'For each item, create a card: Front=What is X? Back=X is...'")
    lines = []
    try:
        while True:
            line = input("  ")
            lines.append(line)
    except EOFError:
        pass
    card_format = "\n".join(lines) if lines else f"Generate cards about {name}."

    data = {
        "name": name,
        "slug": slug,
        "enabled": True,
        "description": description,
        "cards_per_run": cards_per_run,
        "deck": deck,
        "card_type": "Basic",
        "tags_base": [slug.replace("_", "-")],
        "research_strategy": {
            "search_queries": queries,
        },
        "card_format": card_format,
    }

    TOPICS_DIR.mkdir(exist_ok=True)
    path = TOPICS_DIR / f"{slug}.yaml"
    _save_topic(path, data)
    print(f"\nCreated: topics/{slug}.yaml")
    print(f"Edit with: python topics.py edit {slug}")
    print(f"Test the agent with: bash run_agent.sh --dry-run")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Manage Anki agent research topics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list",    help="List all topics")
    show_p = sub.add_parser("show",    help="Show full topic config")
    show_p.add_argument("slug")
    en_p = sub.add_parser("enable",  help="Enable a topic")
    en_p.add_argument("slug")
    dis_p = sub.add_parser("disable", help="Disable a topic")
    dis_p.add_argument("slug")
    sub.add_parser("add",     help="Add a new topic (interactive)")
    rm_p = sub.add_parser("remove",  help="Remove a topic")
    rm_p.add_argument("slug")
    ed_p = sub.add_parser("edit",    help="Open topic file in $EDITOR")
    ed_p.add_argument("slug")

    args = parser.parse_args()

    commands = {
        "list":    cmd_list,
        "show":    cmd_show,
        "enable":  cmd_enable,
        "disable": cmd_disable,
        "add":     cmd_add,
        "remove":  cmd_remove,
        "edit":    cmd_edit,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
