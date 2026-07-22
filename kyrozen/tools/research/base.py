"""Base abstractions for research tools in Kyrozen Phase 4."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from kyrozen.research.models import ResearchSource


class SearchProvider(ABC):
    """Abstract base for external search providers."""

    name: str = ""

    @abstractmethod
    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        """Return a list of ResearchSource objects for the given query."""
        ...

    @property
    def available(self) -> bool:
        """Return True if this provider is configured and ready."""
        return True


class UnconfiguredSearchProvider(SearchProvider):
    """Placeholder provider used when no real search API is configured."""

    def __init__(self, name: str, setup_hint: str) -> None:
        self.name = name
        self.setup_hint = setup_hint

    @property
    def available(self) -> bool:
        return False

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> list[ResearchSource]:
        return [
            ResearchSource(
                title=f"{self.name} is not configured",
                url="",
                source_type="web_page",
                summary=self.setup_hint,
                related_claim="No external data available.",
                confidence="low",
                fact_type="unknown",
            )
        ]
