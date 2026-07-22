"""Market Research module for Kyrozen Phase 4."""

from .models import (
    OPPORTUNITY_DECISIONS,
    Competitor,
    MarketGap,
    MarketResearchReport,
    ResearchPlan,
    ResearchSource,
)

__all__ = [
    "OPPORTUNITY_DECISIONS",
    "ResearchPlan",
    "ResearchSource",
    "Competitor",
    "MarketGap",
    "MarketResearchReport",
]


def __getattr__(name: str):
    """Lazy import MarketResearchAgent to avoid circular imports."""
    if name == "MarketResearchAgent":
        from .agent import MarketResearchAgent

        return MarketResearchAgent
    if name == "ResearchSession":
        from .state import ResearchSession

        return ResearchSession
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
