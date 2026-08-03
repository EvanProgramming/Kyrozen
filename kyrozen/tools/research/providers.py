"""Concrete search providers for Kyrozen Phase 4.

Each provider wraps an external search service and returns ResearchSource objects.
When the required API key is missing, the provider falls back to an
UnconfiguredSearchProvider-like behavior instead of fabricating results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from kyrozen.research.models import ResearchSource

from .base import SearchProvider, UnconfiguredSearchProvider


def _epoch_to_iso(value: Any) -> str:
    """Normalize public API epoch timestamps for freshness calculations."""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _http_failure_source(provider: str, source_type: str, error: Exception) -> ResearchSource:
    """Preserve provider rate-limit semantics instead of flattening all HTTP errors."""
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        title = f"{provider} rate limited"
        summary = f"Provider returned HTTP 429: {error}"
    else:
        title = f"{provider} search failed"
        summary = f"HTTP {status_code}: {error}" if status_code else str(error)
    return ResearchSource(
        title=title,
        url="",
        source_type=source_type,
        summary=summary,
        confidence="low",
        fact_type="unknown",
    )


@dataclass(frozen=True)
class ProviderStatus:
    """Operational state surfaced by research runs and the workbench."""

    provider: str
    status: str  # success / failed / rate_limited / unconfigured
    detail: str = ""
    attempts: int = 0


class ConfiguredJsonProvider(SearchProvider):
    """Small adapter for providers whose endpoint is deployment-configured.

    It intentionally refuses to guess an endpoint or fabricate results when
    the deployment has not configured one.
    """

    source_type = "web_page"

    def __init__(self, name: str, env_name: str, source_type: str, endpoint: str | None = None) -> None:
        self.name = name
        self.env_name = env_name
        self.source_type = source_type
        self.endpoint = endpoint or os.environ.get(env_name, "")

    @property
    def available(self) -> bool:
        return bool(self.endpoint)

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        if not self.endpoint:
            return [ResearchSource(
                title=f"{self.name} is not configured", source_type=self.source_type,
                summary=f"Set {self.env_name} to enable this source.", fact_type="unknown", confidence="low",
            )]
        try:
            import requests
            response = requests.get(self.endpoint, params={"q": query, "query": query, "limit": limit}, timeout=30)
            if response.status_code == 429:
                return [ResearchSource(title=f"{self.name} rate limited", source_type=self.source_type, summary="Provider returned HTTP 429.", fact_type="unknown", confidence="low")]
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return [ResearchSource(title=f"{self.name} search failed", source_type=self.source_type, summary=str(exc), fact_type="unknown", confidence="low")]
        rows = data.get("results", data.get("items", data if isinstance(data, list) else []))
        return [self._source_from_row(row, query) for row in rows[:limit] if isinstance(row, dict)]

    def _source_from_row(self, row: dict[str, Any], query: str) -> ResearchSource:
        """Normalize provider-specific public fields without inventing values."""
        def first(*keys: str) -> Any:
            for key in keys:
                value = row.get(key)
                if value is not None and value != "":
                    return value
            return ""

        source = ResearchSource(
            title=str(first("title", "name")),
            url=str(first("url", "link")),
            source_type=self.source_type,
            summary=str(first("summary", "description", "abstract")),
            related_claim=f"Search result for: {query}",
            fact_type="fact",
            confidence="medium",
        )
        if self.source_type == "patent":
            source.patent_number = str(first("patent_number", "publication_number", "publicationNumber", "patentNumber"))
            source.applicant = str(first("applicant", "applicant_name", "assignee", "assignee_name"))
            source.publish_date = str(first("publish_date", "publication_date", "filing_date", "date"))
            source.legal_status = str(first("legal_status", "legalStatus", "status"))
        elif self.source_type == "crowdfunding":
            source.target_amount = str(first("target_amount", "goal", "goal_amount", "target"))
            source.raised_amount = str(first("raised_amount", "pledged", "amount_raised", "raised"))
            backers = first("backers", "backer_count", "supporters")
            try:
                source.backers = int(backers) if backers != "" else None
            except (TypeError, ValueError):
                source.backers = None
            source.delivery_status = str(first("delivery_status", "delivery", "status"))
            source.platform = str(first("platform", "site", "source"))
        return source


class PatentSearchProvider(ConfiguredJsonProvider):
    name = "patent"

    def __init__(self, endpoint: str | None = None) -> None:
        super().__init__("patent", "PATENT_SEARCH_URL", "patent", endpoint)


class CrowdfundingSearchProvider(ConfiguredJsonProvider):
    name = "crowdfunding"

    def __init__(self, endpoint: str | None = None) -> None:
        super().__init__("crowdfunding", "CROWDFUNDING_SEARCH_URL", "crowdfunding", endpoint)


class CommunitySearchProvider(SearchProvider):
    """Community adapter using public endpoints and explicit failure records."""

    name = "community"

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        try:
            import requests
            response = requests.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": query, "hitsPerPage": limit},
                timeout=30,
            )
            if response.status_code == 429:
                return [ResearchSource(title="Community search rate limited", source_type="community", summary="HTTP 429", fact_type="unknown", confidence="low")]
            response.raise_for_status()
            hits = response.json().get("hits", [])
        except Exception as exc:
            return [ResearchSource(title="Community search failed", source_type="community", summary=str(exc), fact_type="unknown", confidence="low")]
        return [ResearchSource(
            title=hit.get("title") or hit.get("story_title") or "Community post",
            url=hit.get("url") or (f"https://news.ycombinator.com/item?id={hit.get('objectID')}" if hit.get("objectID") else ""),
            source_type="community",
            summary=hit.get("story_text") or hit.get("comment_text") or "",
            related_claim=f"Community discussion for: {query}",
            published_at=hit.get("created_at", ""),
            engagement=hit.get("points") or hit.get("num_comments"),
            platform="hacker_news",
            fact_type="fact",
            confidence="medium",
        ) for hit in hits[:limit]]


class RedditSearchProvider(SearchProvider):
    """Search public Reddit results without requiring an authenticated client."""

    name = "reddit"

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        try:
            import requests
            response = requests.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "limit": limit, "sort": "relevance", "raw_json": 1},
                headers={"User-Agent": "Kyrozen-Research/1.0"},
                timeout=30,
            )
            response.raise_for_status()
            children = (response.json().get("data") or {}).get("children", [])
        except Exception as exc:
            return [_http_failure_source(self.name, "community", exc)]
        return [ResearchSource(
            title=str((item.get("data") or {}).get("title") or "Reddit discussion"),
            url=str((item.get("data") or {}).get("url") or ""),
            source_type="community",
            summary=str((item.get("data") or {}).get("selftext") or ""),
            related_claim=f"Reddit discussion for: {query}",
            published_at=_epoch_to_iso((item.get("data") or {}).get("created_utc")),
            engagement=int((item.get("data") or {}).get("score") or 0) + int((item.get("data") or {}).get("num_comments") or 0),
            platform="reddit",
            fact_type="fact",
            confidence="medium",
        ) for item in children[:limit] if isinstance(item, dict)]


class GitHubDiscussionsProvider(SearchProvider):
    """Search GitHub Discussions through the public issues search endpoint."""

    name = "github_discussions"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        try:
            import requests
            headers = {"Accept": "application/vnd.github+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            response = requests.get(
                "https://api.github.com/search/issues",
                params={"q": f"{query} type:discussion", "per_page": limit},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            rows = response.json().get("items", [])
        except Exception as exc:
            return [_http_failure_source(self.name, "community", exc)]
        return [ResearchSource(
            title=str(row.get("title", "GitHub Discussion")),
            url=str(row.get("html_url", "")),
            source_type="community",
            summary=str(row.get("body") or ""),
            related_claim=f"GitHub Discussion for: {query}",
            published_at=str(row.get("created_at") or ""),
            engagement=int(row.get("comments") or 0),
            platform="github_discussions",
            fact_type="fact",
            confidence="medium",
        ) for row in rows[:limit] if isinstance(row, dict)]


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
        self.api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")
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
            return [_http_failure_source(self.name, "web_page", e)]

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
        self.api_key = api_key if api_key is not None else os.environ.get("SERPER_API_KEY", "")
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
            return [_http_failure_source(self.name, "web_page", e)]

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
            return [_http_failure_source(self.name, "github", e)]

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
                params={"query": query, "limit": limit, "fields": "title,url,abstract,year,authors,externalIds"},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:  # pragma: no cover
            return [_http_failure_source(self.name, "paper", e)]

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
                    doi=(paper.get("externalIds") or {}).get("DOI", ""),
                    authors=[author.get("name", "") for author in paper.get("authors", [])],
                    year=paper.get("year"),
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
