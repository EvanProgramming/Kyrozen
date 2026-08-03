"""Evidence tracking and confidence assessment for problem discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .brief import CONFIDENCE_LEVELS, EVIDENCE_SOURCES


@dataclass
class Evidence:
    """A single recorded evidence item tied to a project."""

    claim: str
    original_text: str = ""
    summary: str = ""
    source: str = "user_statement"  # user_statement / ai_inference / external_evidence
    source_name: str = ""
    verified: bool = False
    confidence: str = "medium"  # low / medium / high
    notes: str = ""
    evidence_type: str = "user_statement"
    source_url: str = ""
    observed_at: str = ""
    target_audience: str = ""
    related_question: str = ""
    counter_evidence: list[str] = field(default_factory=list)
    claim_type: str = "unknown"  # fact / opinion / inference / unknown
    status: str = "active"  # active / invalid / merged / deleted

    def __post_init__(self) -> None:
        if self.source not in EVIDENCE_SOURCES:
            raise ValueError(f"Invalid evidence source '{self.source}'")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")
        valid_types = {"interview", "observation", "survey", "screenshot", "video", "public_source", "user_statement", "ai_inference", "external_evidence"}
        if self.evidence_type not in valid_types:
            raise ValueError(f"Invalid evidence_type '{self.evidence_type}'")
        if self.status not in {"active", "invalid", "merged", "deleted"}:
            raise ValueError(f"Invalid evidence status '{self.status}'")
        if self.claim_type not in {"fact", "opinion", "inference", "unknown"}:
            raise ValueError(f"Invalid claim_type '{self.claim_type}'")
        if not self.observed_at:
            self.observed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "original_text": self.original_text,
            "summary": self.summary,
            "source": self.source,
            "source_name": self.source_name,
            "verified": self.verified,
            "confidence": self.confidence,
            "notes": self.notes,
            "evidence_type": self.evidence_type,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "target_audience": self.target_audience,
            "related_question": self.related_question,
            "counter_evidence": list(self.counter_evidence),
            "claim_type": self.claim_type,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        return cls(
            claim=data.get("claim", ""),
            original_text=data.get("original_text", ""),
            summary=data.get("summary", ""),
            source=data.get("source", "user_statement"),
            source_name=data.get("source_name", ""),
            verified=data.get("verified", False),
            confidence=data.get("confidence", "medium"),
            notes=data.get("notes", ""),
            evidence_type=data.get("evidence_type", data.get("source", "user_statement")),
            source_url=data.get("source_url", ""),
            observed_at=data.get("observed_at", ""),
            target_audience=data.get("target_audience", ""),
            related_question=data.get("related_question", ""),
            counter_evidence=list(data.get("counter_evidence") or []),
            claim_type=data.get("claim_type", "unknown"),
            status=data.get("status", "active"),
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
