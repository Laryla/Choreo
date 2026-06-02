"""
Web search and URL fetch tools for the research sub-agent.

Search backend selection:
  TAVILY_API_KEY set + tavily-python installed  → Tavily (best quality)
  TAVILY_API_KEY set + tavily-python missing    → warn + fallback DuckDuckGo
  TAVILY_API_KEY empty + duckduckgo-search installed → DuckDuckGo (default)
  both missing                                  → stub that explains how to install
"""
from __future__ import annotations

import logging
import re

from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)


def build_web_search_tool() -> BaseTool:
    """Return the best available web search tool."""
    from choreo.config import settings

    if settings.TAVILY_API_KEY:
        try:
            import os
            import tavily  # noqa: F401
            from langchain_community.tools.tavily_search import TavilySearchResults
            os.environ.setdefault("TAVILY_API_KEY", settings.TAVILY_API_KEY)
            logger.info("Web search: using Tavily")
            return TavilySearchResults(max_results=5)
        except ImportError:
            logger.warning(
                "TAVILY_API_KEY is set but tavily-python or langchain-community is not installed. "
                "Falling back to DuckDuckGo. Run: uv add tavily-python langchain-community"
            )

    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        logger.info("Web search: using DuckDuckGo")
        return DuckDuckGoSearchRun()
    except ImportError:
        pass

    # Graceful degradation stub
    @tool
    def web_search(query: str) -> str:  # type: ignore[misc]
        """Search the web (unavailable — install langchain-community and duckduckgo-search)."""
        return (
            "Web search is unavailable. Install dependencies:\n"
            "  uv add langchain-community duckduckgo-search\n"
            "Or for Tavily (higher quality):\n"
            "  uv add tavily-python langchain-community\n"
            "  Then set TAVILY_API_KEY in .env"
        )

    return web_search  # type: ignore[return-value]


@tool
async def fetch_url(url: str) -> str:
    """
    Fetch the text content of a URL.

    Use this to retrieve documentation pages, GitHub READMEs, blog posts,
    or any public web page. Returns the first 8000 characters of the body.

    Args:
        url: The full URL to fetch (must start with http:// or https://).
    """
    if not url.startswith(("http://", "https://")):
        return f"Invalid URL: must start with http:// or https://. Got: {url!r}"
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "ChoreoResearch/1.0"})
            resp.raise_for_status()
            text = resp.text
        # Strip HTML tags and collapse whitespace
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000]
    except Exception as exc:
        logger.warning("fetch_url failed for %r: %s", url, exc)
        return f"Failed to fetch {url!r}: {exc}"


# Instantiate the search tool at module load — shared across callers
web_search: BaseTool = build_web_search_tool()
