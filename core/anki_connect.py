import logging
from typing import List, Optional, Tuple

import requests

from .models import Card, CardType

logger = logging.getLogger(__name__)


class AnkiConnectError(Exception):
    pass


class AnkiConnect:
    """Thin client for the AnkiConnect add-on REST API."""

    def __init__(self, url: str = "http://localhost:8765", version: int = 6):
        self.url = url
        self.version = version

    def _request(self, action: str, **params) -> object:
        payload = {"action": action, "version": self.version, "params": params}
        try:
            response = requests.post(self.url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.ConnectionError:
            raise AnkiConnectError(
                f"Cannot connect to AnkiConnect at {self.url}. "
                "Make sure Anki is running with the AnkiConnect add-on installed "
                "(add-on ID: 2055492159)."
            )
        result = response.json()
        if result.get("error"):
            raise AnkiConnectError(f"AnkiConnect returned error: {result['error']}")
        return result["result"]

    def is_available(self) -> bool:
        try:
            self._request("version")
            return True
        except Exception:
            return False

    def ensure_deck(self, deck_name: str):
        existing = self._request("deckNames")
        if deck_name not in existing:
            self._request("createDeck", deck=deck_name)
            logger.info(f"Created deck: {deck_name!r}")

    def add_card(self, card: Card) -> Optional[int]:
        """Add a single card. Returns AnkiConnect note ID, or None for duplicates."""
        self.ensure_deck(card.deck_name)

        if card.card_type == CardType.CLOZE:
            note = {
                "deckName": card.deck_name,
                "modelName": "Cloze",
                "fields": {"Text": card.front, "Extra": card.back},
                "tags": card.tags,
                "options": {"allowDuplicate": False},
            }
        else:
            note = {
                "deckName": card.deck_name,
                "modelName": "Basic",
                "fields": {"Front": card.front, "Back": card.back},
                "tags": card.tags,
                "options": {"allowDuplicate": False},
            }

        result = self._request("addNote", note=note)
        return result  # note ID (int) or None if duplicate

    def add_cards(self, cards: List[Card]) -> Tuple[List[int], List[int]]:
        """
        Import a list of cards.
        Returns (succeeded_db_ids, failed_db_ids) — IDs refer to our SQLite card.id.
        Duplicates are treated as successes (already in Anki).
        """
        succeeded, failed = [], []
        for card in cards:
            try:
                self.add_card(card)
                succeeded.append(card.id)
                logger.debug(f"Imported card {card.id}: {card.front[:50]!r}")
            except AnkiConnectError as e:
                logger.warning(f"Failed to import card {card.id}: {e}")
                failed.append(card.id)
        return succeeded, failed

    def sync(self):
        """Trigger AnkiWeb sync (non-critical — failure is logged, not raised)."""
        try:
            self._request("sync")
            logger.info("Triggered AnkiWeb sync")
        except AnkiConnectError as e:
            logger.warning(f"AnkiWeb sync failed (non-critical): {e}")

    def get_deck_names(self) -> List[str]:
        return self._request("deckNames")
