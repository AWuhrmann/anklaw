import pytest
import requests
from unittest.mock import MagicMock, patch

from core.anki_connect import AnkiConnect, AnkiConnectError
from core.models import Card, CardType


@pytest.fixture
def anki():
    return AnkiConnect("http://localhost:8765")


@pytest.fixture
def basic_card():
    return Card(
        id=1, front="What is Python?", back="A language.",
        tags=["test"], deck_name="Test::Deck", card_type=CardType.BASIC,
    )


@pytest.fixture
def cloze_card():
    return Card(
        id=2,
        front="The {{c1::mitochondria}} is the powerhouse of the cell.",
        back="Biology extra info.",
        tags=["biology"], deck_name="Test::Deck", card_type=CardType.CLOZE,
    )


def _ok(result):
    m = MagicMock()
    m.json.return_value = {"result": result, "error": None}
    m.raise_for_status = MagicMock()
    return m


def _err(message):
    m = MagicMock()
    m.json.return_value = {"result": None, "error": message}
    m.raise_for_status = MagicMock()
    return m


class TestAnkiConnect:
    def test_is_available_true(self, anki):
        with patch("requests.post", return_value=_ok(6)):
            assert anki.is_available() is True

    def test_is_available_false_connection_error(self, anki):
        with patch("requests.post", side_effect=requests.ConnectionError()):
            assert anki.is_available() is False

    def test_is_available_false_on_error_response(self, anki):
        with patch("requests.post", return_value=_err("some error")):
            assert anki.is_available() is False

    def test_add_basic_card_success(self, anki, basic_card):
        with patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _ok(["Test::Deck"]),  # deckNames — deck exists
                _ok(12345),           # addNote
            ]
            result = anki.add_card(basic_card)
        assert result == 12345

    def test_add_card_creates_missing_deck(self, anki, basic_card):
        with patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _ok([]),              # deckNames — empty
                _ok(None),            # createDeck
                _ok(12345),           # addNote
            ]
            anki.add_card(basic_card)
        assert mock_post.call_count == 3

    def test_add_cloze_card(self, anki, cloze_card):
        with patch("requests.post") as mock_post:
            mock_post.side_effect = [
                _ok(["Test::Deck"]),
                _ok(99999),
            ]
            result = anki.add_card(cloze_card)
        assert result == 99999
        # Verify Cloze model was used
        call_args = mock_post.call_args_list[1]
        note = call_args.kwargs["json"]["params"]["note"]
        assert note["modelName"] == "Cloze"
        assert "Text" in note["fields"]

    def test_add_cards_all_succeed(self, anki, basic_card):
        cards = [
            Card(id=1, front="Q1", back="A1", deck_name="T", card_type=CardType.BASIC),
            Card(id=2, front="Q2", back="A2", deck_name="T", card_type=CardType.BASIC),
        ]
        with patch.object(anki, "add_card", side_effect=[1111, 2222]):
            succeeded, failed = anki.add_cards(cards)
        assert succeeded == [1, 2]
        assert failed == []

    def test_add_cards_partial_failure(self, anki):
        cards = [
            Card(id=1, front="Q1", back="A1", deck_name="T", card_type=CardType.BASIC),
            Card(id=2, front="Q2", back="A2", deck_name="T", card_type=CardType.BASIC),
            Card(id=3, front="Q3", back="A3", deck_name="T", card_type=CardType.BASIC),
        ]
        with patch.object(anki, "add_card", side_effect=[1111, AnkiConnectError("err"), 3333]):
            succeeded, failed = anki.add_cards(cards)
        assert succeeded == [1, 3]
        assert failed == [2]

    def test_raises_anki_connect_error(self, anki):
        with patch("requests.post", return_value=_err("deck not found")):
            with pytest.raises(AnkiConnectError, match="deck not found"):
                anki._request("someAction")

    def test_connection_error_raises_with_helpful_message(self, anki):
        with patch("requests.post", side_effect=requests.ConnectionError()):
            with pytest.raises(AnkiConnectError, match="Cannot connect"):
                anki._request("version")

    def test_sync_does_not_raise_on_failure(self, anki):
        with patch.object(anki, "_request", side_effect=AnkiConnectError("sync failed")):
            anki.sync()  # should log warning, not raise
