import json
import logging
import os
import time
import uuid
from typing import List, Optional, Tuple

from .config import GenerationConfig
from .models import Batch, Card, CardType

logger = logging.getLogger(__name__)

_BASIC_PROMPT = """\
You are an expert Anki flashcard creator. Create exactly {n} high-quality Anki flashcards based on the following instructions:

{instructions}

Rules:
- Each card must test exactly ONE concept
- Front: a clear, specific question or prompt
- Back: a concise, accurate answer (2-4 sentences max)
- Avoid trivial yes/no questions
- Tags: lowercase, specific, useful for filtering (2-4 per card)
- Generate DIVERSE cards — do not repeat similar questions

Output ONLY valid JSON, no markdown fences, no explanation:
{{"cards": [{{"front": "...", "back": "...", "tags": ["tag1", "tag2"]}}]}}"""

_CLOZE_PROMPT = """\
You are an expert Anki flashcard creator. Create exactly {n} high-quality Anki cloze deletion flashcards based on the following instructions:

{instructions}

Rules:
- Use {{{{c1::...}}}} syntax for cloze deletions (double braces)
- Each card tests exactly ONE important concept
- Back (Extra): additional context or explanation
- Tags: lowercase, specific, useful for filtering (2-4 per card)
- Generate DIVERSE cards — do not repeat similar facts

Output ONLY valid JSON, no markdown fences, no explanation:
{{"cards": [{{"front": "The {{{{c1::mitochondria}}}} is the powerhouse of the cell.", "back": "Extra context here.", "tags": ["tag1"]}}]}}"""


class CardGenerator:
    def __init__(self, config: GenerationConfig):
        self.config = config
        self._client = None

    def generate(
        self,
        n: Optional[int] = None,
        instructions: Optional[str] = None,
        research_context: str = "",
        dry_run: bool = False,
    ) -> Tuple[Batch, List[Card]]:
        n = n or self.config.cards_per_day
        instructions = instructions or self.config.topic_instructions

        if research_context:
            instructions = (
                f"{instructions}\n\nRecent research context to incorporate:\n{research_context}"
            )

        batch = Batch(
            id=str(uuid.uuid4()),
            cards_requested=n,
            topic_snapshot=instructions[:500],
            llm_model=self.config.llm_model,
        )

        if dry_run or self.config.llm_provider == "_mock":
            logger.info(f"[DRY RUN] Generating {n} mock cards")
            cards = self._mock_cards(n)
            batch.cards_generated = len(cards)
            return batch, cards

        cards = self._generate_with_retry(n, instructions)
        batch.cards_generated = len(cards)
        logger.info(f"Generated {len(cards)} cards in batch {batch.id[:8]}")
        return batch, cards

    def test_connection(self) -> bool:
        """Verify the LLM API key and model are reachable."""
        try:
            client = self._get_client()
            if self.config.llm_provider == "anthropic":
                client.messages.create(
                    model=self.config.llm_model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Reply with: OK"}],
                )
            elif self.config.llm_provider == "openai":
                client.chat.completions.create(
                    model=self.config.llm_model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Reply with: OK"}],
                )
            return True
        except Exception as e:
            logger.error(f"LLM connection test failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self.config.llm_provider == "anthropic":
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        elif self.config.llm_provider == "openai":
            import openai
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self._client = openai.OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.llm_provider!r}")
        return self._client

    def _generate_with_retry(self, n: int, instructions: str) -> List[Card]:
        last_err = None
        for attempt in range(self.config.max_retries):
            try:
                return self._call_llm(n, instructions)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                last_err = e
                logger.warning(f"Generation attempt {attempt + 1}/{self.config.max_retries} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(
            f"Failed to generate cards after {self.config.max_retries} attempts. Last error: {last_err}"
        )

    def _call_llm(self, n: int, instructions: str) -> List[Card]:
        card_type = CardType(self.config.card_type)
        template = _CLOZE_PROMPT if card_type == CardType.CLOZE else _BASIC_PROMPT
        prompt = template.format(n=n, instructions=instructions)

        if self.config.llm_provider == "anthropic":
            raw = self._call_anthropic(prompt)
        else:
            raw = self._call_openai(prompt)

        return self._parse_response(raw, expected_n=n)

    def _call_anthropic(self, prompt: str) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self.config.llm_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _call_openai(self, prompt: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.llm_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def _parse_response(self, raw: str, expected_n: int) -> List[Card]:
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)
        cards_data = data["cards"]

        if len(cards_data) < expected_n * 0.5:
            raise ValueError(
                f"Only got {len(cards_data)} cards but expected ~{expected_n}. "
                "The model may have truncated its response."
            )

        card_type = CardType(self.config.card_type)
        return [
            Card(
                front=item["front"].strip(),
                back=item["back"].strip(),
                tags=item.get("tags", []),
                deck_name=self.config.deck_name,
                card_type=card_type,
            )
            for item in cards_data
        ]

    def _mock_cards(self, n: int) -> List[Card]:
        card_type = CardType(self.config.card_type)
        return [
            Card(
                front=f"[MOCK] Question {i + 1}: What is concept {i + 1}?",
                back=f"[MOCK] Answer {i + 1}: This is the explanation of concept {i + 1}.",
                tags=["mock", "test"],
                deck_name=self.config.deck_name,
                card_type=card_type,
            )
            for i in range(n)
        ]
