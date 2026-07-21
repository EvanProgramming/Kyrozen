"""Evidence tracking and confidence assessment for problem discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .brief import CONFIDENCE_LEVELS, EVIDENCE_SOURCES


@dataclass
class Evidence:
    """A single recorded evidence item tied to a project."""

    claim: str
    source: str = "user_statement"  # user_statement / ai_inference / external_evidence
    verified: bool = False
    confidence: str = "medium"  # low / medium / high
    notes: str = ""

    def __post_init__(self) -> None:
        if self.source not in EVIDENCE_SOURCES:
            raise ValueError(f"Invalid evidence source '{self.source}'")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "source": self.source,
            "verified": self.verified,
            "confidence": self.confidence,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        return cls(
            claim=data.get("claim", ""),
            source=data.get("source", "user_statement"),
            verified=data.get("verified", False),
            confidence=data.get("confidence", "medium"),
            notes=data.get("notes", ""),
        )


def assess_confidence(brief_data: dict[str, Any]) -> tuple[str, str]:
    """Return (confidence_level, reason) based on brief content.

    Simple heuristic used by the agent/tooling to recommend a confidence level.
    """
    score = 0
    max_score = 6
    fields = [
        "target_user",
        "scenario",
        "surface_problem",
        "deep_need",
        "current_solution",
        "current_solution_problem",
    ]
    for field in fields:
        value = brief_data.get(field, "")
        if isinstance(value, str) and value.strip():
            score += 1

    assumptions = brief_data.get("unknown_assumptions") or []
    unverified_count = sum(1 for a in assumptions if not a.get("verified", False))

    if score <= 2 or unverified_count >= 3:
        return "low", f"Only {score}/{max_score} key fields are filled and {unverified_count} assumptions remain unverified."
    if score <= 4 or unverified_count >= 1:
        return "medium", f"{score}/{max_score} key fields filled, but {unverified_count} assumptions need validation."
    return "high", f"{score}/{max_score} key fields filled with few unverified assumptions."
