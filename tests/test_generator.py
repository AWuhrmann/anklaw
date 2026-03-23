import json
import pytest
from unittest.mock import MagicMock, patch

from core.config import GenerationConfig
from core.generator import CardGenerator
from core.models import CardType


@pytest.fixture
def cfg():
    return GenerationConfig(
        cards_per_day=5,
        topic_instructions="Generate flashcards about Python.",
        deck_name="Test",
        card_type="Basic",
        llm_provider="anthropic",
        llm_model="claude-opus-4-6",
        max_retries=2,
    )


def _json_response(n: int) -> str:
    return json.dumps({
        "cards": [{"front": f"Q{i}", "back": f"A{i}", "tags": ["test"]} for i in range(n)]
    })


class TestCardGenerator:
    def test_dry_run_returns_mock_cards(self, cfg):
        gen = CardGenerator(cfg)
        batch, cards = gen.generate(n=5, dry_run=True)
        assert len(cards) == 5
        assert batch.cards_generated == 5
        assert all(c.deck_name == "Test" for c in cards)
        assert all(c.card_type == CardType.BASIC for c in cards)

    def test_mock_provider(self, cfg):
        cfg.llm_provider = "_mock"
        gen = CardGenerator(cfg)
        batch, cards = gen.generate(n=3)
        assert len(cards) == 3

    def test_cloze_type(self, cfg):
        cfg.card_type = "Cloze"
        gen = CardGenerator(cfg)
        _, cards = gen.generate(n=3, dry_run=True)
        assert all(c.card_type == CardType.CLOZE for c in cards)

    def test_parse_valid_json(self, cfg):
        gen = CardGenerator(cfg)
        raw = _json_response(5)
        cards = gen._parse_response(raw, expected_n=5)
        assert len(cards) == 5
        assert cards[0].front == "Q0"
        assert cards[0].back == "A0"

    def test_parse_strips_markdown_fences(self, cfg):
        gen = CardGenerator(cfg)
        raw = f"```json\n{_json_response(2)}\n```"
        cards = gen._parse_response(raw, expected_n=2)
        assert len(cards) == 2

    def test_parse_too_few_cards_raises(self, cfg):
        gen = CardGenerator(cfg)
        raw = _json_response(1)
        with pytest.raises(ValueError, match="Only got"):
            gen._parse_response(raw, expected_n=10)

    def test_parse_invalid_json_raises(self, cfg):
        gen = CardGenerator(cfg)
        with pytest.raises(json.JSONDecodeError):
            gen._parse_response("not json at all", expected_n=1)

    def test_batch_metadata(self, cfg):
        gen = CardGenerator(cfg)
        batch, cards = gen.generate(n=4, dry_run=True)
        assert batch.id is not None
        assert batch.cards_requested == 4
        assert batch.cards_generated == len(cards)
        assert batch.llm_model == cfg.llm_model

    def test_anthropic_integration(self, cfg):
        """Verify Anthropic client is called with correct parameters."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=_json_response(5))]
        )
        gen = CardGenerator(cfg)
        gen._client = mock_client

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            _, cards = gen.generate(n=5)

        assert len(cards) == 5
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == cfg.llm_model
        assert call_kwargs["max_tokens"] > 0

    def test_retry_on_bad_json(self, cfg):
        """Generator retries when LLM returns malformed JSON."""
        gen = CardGenerator(cfg)

        # Patch _call_llm to use a two-attempt mock
        good_response = _json_response(5)
        with patch.object(gen, "_call_llm", side_effect=[
            json.JSONDecodeError("bad", "", 0),
            gen._parse_response(good_response, 5),
        ]):
            batch, cards = gen.generate(n=5)
        assert len(cards) == 5
