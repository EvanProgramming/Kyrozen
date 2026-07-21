"""Problem Brief data model for Kyrozen Phase 3.

A Problem Brief captures the understanding of a user problem before any
product design or market research begins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CONFIDENCE_LEVELS = {"low", "medium", "high"}

PROBLEM_DECISIONS = {
    "continue_research",
    "need_more_information",
    "existing_solution_enough",
    "problem_not_clear",
    "not_suitable_for_product",
}

EVIDENCE_SOURCES = {
    "user_statement",
    "ai_inference",
    "external_evidence",
}


@dataclass
class EvidenceItem:
    """A single piece of evidence/assumption tracked in a brief."""

    claim: str
    source: str = "user_statement"  # user_statement / ai_inference / external_evidence
    verified: bool = False

    def __post_init__(self) -> None:
        if self.source not in EVIDENCE_SOURCES:
            raise ValueError(f"Invalid evidence source '{self.source}'")

    def to_dict(self) -> dict[str, Any]:
        return {"claim": self.claim, "source": self.source, "verified": self.verified}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceItem":
        return cls(
            claim=data.get("claim", ""),
            source=data.get("source", "user_statement"),
            verified=data.get("verified", False),
        )


@dataclass
class ProblemBrief:
    """Structured summary of a discovered problem."""

    title: str = ""
    target_user: str = ""
    scenario: str = ""
    surface_problem: str = ""
    deep_need: str = ""
    current_solution: str = ""
    current_solution_problem: str = ""
    frequency: str = ""
    impact: str = ""
    unknown_assumptions: list[EvidenceItem] = field(default_factory=list)
    opportunity_direction: str = ""
    confidence: str = "low"
    confidence_reason: str = ""
    decision: str = "need_more_information"
    decision_reason: str = ""

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")
        if self.decision not in PROBLEM_DECISIONS:
            raise ValueError(f"Invalid decision '{self.decision}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "target_user": self.target_user,
            "scenario": self.scenario,
            "surface_problem": self.surface_problem,
            "deep_need": self.deep_need,
            "current_solution": self.current_solution,
            "current_solution_problem": self.current_solution_problem,
            "frequency": self.frequency,
            "impact": self.impact,
            "unknown_assumptions": [item.to_dict() for item in self.unknown_assumptions],
            "opportunity_direction": self.opportunity_direction,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemBrief":
        assumptions = data.get("unknown_assumptions") or []
        return cls(
            title=data.get("title", ""),
            target_user=data.get("target_user", ""),
            scenario=data.get("scenario", ""),
            surface_problem=data.get("surface_problem", ""),
            deep_need=data.get("deep_need", ""),
            current_solution=data.get("current_solution", ""),
            current_solution_problem=data.get("current_solution_problem", ""),
            frequency=data.get("frequency", ""),
            impact=data.get("impact", ""),
            unknown_assumptions=[EvidenceItem.from_dict(a) for a in assumptions],
            opportunity_direction=data.get("opportunity_direction", ""),
            confidence=data.get("confidence", "low"),
            confidence_reason=data.get("confidence_reason", ""),
            decision=data.get("decision", "need_more_information"),
            decision_reason=data.get("decision_reason", ""),
        )

    def merge(self, other: "ProblemBrief") -> "ProblemBrief":
        """Return a new brief where non-empty fields from other override self."""
        def pick(self_value: Any, other_value: Any) -> Any:
            if other_value is None:
                return self_value
            if isinstance(other_value, (list, dict)) and not other_value:
                return self_value
            if isinstance(other_value, str) and not other_value.strip():
                return self_value
            return other_value

        merged_assumptions = list(self.unknown_assumptions)
        existing_claims = {a.claim for a in merged_assumptions}
        for item in other.unknown_assumptions:
            if item.claim and item.claim not in existing_claims:
                merged_assumptions.append(item)

        return ProblemBrief(
            title=pick(self.title, other.title),
            target_user=pick(self.target_user, other.target_user),
            scenario=pick(self.scenario, other.scenario),
            surface_problem=pick(self.surface_problem, other.surface_problem),
            deep_need=pick(self.deep_need, other.deep_need),
            current_solution=pick(self.current_solution, other.current_solution),
            current_solution_problem=pick(self.current_solution_problem, other.current_solution_problem),
            frequency=pick(self.frequency, other.frequency),
            impact=pick(self.impact, other.impact),
            unknown_assumptions=merged_assumptions,
            opportunity_direction=pick(self.opportunity_direction, other.opportunity_direction),
            confidence=pick(self.confidence, other.confidence),
            confidence_reason=pick(self.confidence_reason, other.confidence_reason),
            decision=pick(self.decision, other.decision),
            decision_reason=pick(self.decision_reason, other.decision_reason),
        )
