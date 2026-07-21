"""Problem Discovery module for Kyrozen Phase 3."""

from .brief import EvidenceItem, ProblemBrief
from .evidence import Evidence, assess_confidence
from .question_engine import NextQuestion, QuestionEngine
from .state import DiscoverySession

__all__ = [
    "ProblemDiscoveryAgent",
    "ProblemBrief",
    "EvidenceItem",
    "Evidence",
    "assess_confidence",
    "QuestionEngine",
    "NextQuestion",
    "DiscoverySession",
]


def __getattr__(name: str):
    """Lazy import ProblemDiscoveryAgent to avoid circular imports."""
    if name == "ProblemDiscoveryAgent":
        from .agent import ProblemDiscoveryAgent

        return ProblemDiscoveryAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
