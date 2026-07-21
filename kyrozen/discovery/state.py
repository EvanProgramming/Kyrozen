"""Discovery session state for Kyrozen Phase 3.

A DiscoverySession tracks the current Problem Brief, recorded evidence, and
recent Q&A history for a single project. It is designed to be lightweight
and persisted through ProjectMemory and Artifact storage rather than as a
separate database entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .brief import ProblemBrief
from .evidence import Evidence


@dataclass
class DiscoverySession:
    """Runtime state for problem discovery on a single project."""

    project_id: str
    brief: ProblemBrief = field(default_factory=ProblemBrief)
    evidence: list[Evidence] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)

    def update_brief(self, brief: ProblemBrief) -> None:
        """Merge new brief content into the current brief."""
        self.brief = self.brief.merge(brief)

    def add_evidence(self, evidence: Evidence) -> None:
        """Add a new evidence item if the claim is not already recorded."""
        existing_claims = {e.claim for e in self.evidence}
        if evidence.claim and evidence.claim not in existing_claims:
            self.evidence.append(evidence)

    def add_qa(self, question: str, answer: str) -> None:
        """Record a question/answer pair in the session history."""
        self.history.append({"question": question, "answer": answer})
        # Keep only the most recent 20 pairs to avoid context bloat
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "brief": self.brief.to_dict(),
            "evidence": [e.to_dict() for e in self.evidence],
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiscoverySession":
        return cls(
            project_id=data.get("project_id", ""),
            brief=ProblemBrief.from_dict(data.get("brief", {})),
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            history=[dict(item) for item in data.get("history", [])],
        )
