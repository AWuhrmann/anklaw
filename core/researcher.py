import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Researcher:
    """Optional web research context to enrich card generation."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def get_context(self, topic: str, max_results: int = 5) -> str:
        if not self.enabled:
            return ""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning(
                "duckduckgo-search is not installed. "
                "Run: pip install duckduckgo-search  (or set research_enabled: false)"
            )
            return ""

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(topic, max_results=max_results))
            if not results:
                return ""
            parts = [f"**{r['title']}**\n{r['body']}" for r in results]
            context = "\n\n".join(parts)
            logger.info(f"Fetched {len(results)} research results for topic")
            return context
        except Exception as e:
            logger.warning(f"Research fetch failed (non-critical, continuing): {e}")
            return ""
