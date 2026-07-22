"""Concrete search providers for Kyrozen Phase 4.

Each provider wraps an external search service and returns ResearchSource objects.
When the required API key is missing, the provider falls back to an
UnconfiguredSearchProvider-like behavior instead of fabricating results.
"""

from __future__ import annotations

import os
from typing import Any

from kyrozen.research.models import ResearchSource

from .base import SearchProvider, UnconfiguredSearchProvider


class MockSearchProvider(SearchProvider):
    """Deterministic provider for tests and demos."""

    name = "mock"

    def __init__(self, results: list[ResearchSource] | None = None) -> None:
        self.results = results or []

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        return self.results[:limit]


class TavilySearchProvider(SearchProvider):
    """Web search using the Tavily API."""

    name = "tavily"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            self._fallback = UnconfiguredSearchProvider(
                self.name,
                "Set TAVILY_API_KEY environment variable to enable Tavily web search.",
            )
        else:
            self._fallback = None

    @property
    def available(self) -> bool:
        return self._fallback is None

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        if self._fallback is not None:
            return self._fallback.search(query, limit=limit, **kwargs)

        try:
            import requests
        except ImportError:  # pragma: no cover
            return [
                ResearchSource(
                    title="requests not installed",
                    url="",
                    source_type="web_page",
                    summary="Install 'requests' to use Tavily search.",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query, "max_results": limit},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:  # pragma: no cover
            return [
                ResearchSource(
                    title="Tavily search failed",
                    url="",
                    source_type="web_page",
                    summary=f"Error: {e}",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        sources: list[ResearchSource] = []
        for result in data.get("results", [])[:limit]:
            sources.append(
                ResearchSource(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    source_type="web_page",
                    summary=result.get("content", ""),
                    related_claim=f"Search result for: {query}",
                    confidence="medium",
                    fact_type="fact",
                )
            )
        return sources


class SerperSearchProvider(SearchProvider):
    """Web search using the Serper (Google) API."""

    name = "serper"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        if not self.api_key:
            self._fallback = UnconfiguredSearchProvider(
                self.name,
                "Set SERPER_API_KEY environment variable to enable Serper web search.",
            )
        else:
            self._fallback = None

    @property
    def available(self) -> bool:
        return self._fallback is None

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        if self._fallback is not None:
            return self._fallback.search(query, limit=limit, **kwargs)

        try:
            import requests
        except ImportError:  # pragma: no cover
            return [
                ResearchSource(
                    title="requests not installed",
                    url="",
                    source_type="web_page",
                    summary="Install 'requests' to use Serper search.",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        try:
            response = requests.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": limit},
                headers={"X-API-KEY": self.api_key},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:  # pragma: no cover
            return [
                ResearchSource(
                    title="Serper search failed",
                    url="",
                    source_type="web_page",
                    summary=f"Error: {e}",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        sources: list[ResearchSource] = []
        for result in data.get("organic", [])[:limit]:
            sources.append(
                ResearchSource(
                    title=result.get("title", ""),
                    url=result.get("link", ""),
                    source_type="web_page",
                    summary=result.get("snippet", ""),
                    related_claim=f"Search result for: {query}",
                    confidence="medium",
                    fact_type="fact",
                )
            )
        return sources


class GitHubSearchProvider(SearchProvider):
    """Search GitHub repositories and issues."""

    name = "github"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        try:
            import requests
        except ImportError:  # pragma: no cover
            return [
                ResearchSource(
                    title="requests not installed",
                    url="",
                    source_type="github",
                    summary="Install 'requests' to use GitHub search.",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:  # pragma: no cover
            return [
                ResearchSource(
                    title="GitHub search failed",
                    url="",
                    source_type="github",
                    summary=f"Error: {e}",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        sources: list[ResearchSource] = []
        for repo in data.get("items", [])[:limit]:
            sources.append(
                ResearchSource(
                    title=repo.get("full_name", ""),
                    url=repo.get("html_url", ""),
                    source_type="github",
                    summary=repo.get("description", "") or "",
                    related_claim=f"Open source project for: {query}",
                    confidence="medium",
                    fact_type="fact",
                )
            )
        return sources


class SemanticScholarProvider(SearchProvider):
    """Search academic papers via Semantic Scholar."""

    name = "semantic_scholar"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        try:
            import requests
        except ImportError:  # pragma: no cover
            return [
                ResearchSource(
                    title="requests not installed",
                    url="",
                    source_type="paper",
                    summary="Install 'requests' to use Semantic Scholar search.",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            response = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": query, "limit": limit, "fields": "title,url,abstract"},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:  # pragma: no cover
            return [
                ResearchSource(
                    title="Semantic Scholar search failed",
                    url="",
                    source_type="paper",
                    summary=f"Error: {e}",
                    confidence="low",
                    fact_type="unknown",
                )
            ]

        sources: list[ResearchSource] = []
        for paper in data.get("data", [])[:limit]:
            sources.append(
                ResearchSource(
                    title=paper.get("title", ""),
                    url=paper.get("url", ""),
                    source_type="paper",
                    summary=(paper.get("abstract") or "")[:500],
                    related_claim=f"Academic paper for: {query}",
                    confidence="high",
                    fact_type="fact",
                )
            )
        return sources


def get_default_search_provider(
    tavily_api_key: str | None = None,
    serper_api_key: str | None = None,
) -> SearchProvider:
    """Return the best available web search provider based on configuration."""
    tavily = TavilySearchProvider(api_key=tavily_api_key)
    if tavily.available:
        return tavily
    serper = SerperSearchProvider(api_key=serper_api_key)
    if serper.available:
        return serper
    return UnconfiguredSearchProvider(
        "web_search",
        "No web search provider configured. Set TAVILY_API_KEY or SERPER_API_KEY.",
    )
