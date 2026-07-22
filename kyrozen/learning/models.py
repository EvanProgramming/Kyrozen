"""Data models for Kyrozen Phase 9 Project Self-Learning and Proactive Improvement."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_MEMORY_TYPES = {
    "user_preference",
    "user_capability",
    "project_fact",
    "product_decision",
    "validated_success",
    "validated_failure",
    "external_knowledge",
}

VALID_CONFIDENCE_LEVELS = {
    "low",
    "medium",
    "high",
}

VALID_VERIFICATION_STATUSES = {
    "unverified",
    "user_provided",
    "externally_verified",
    "experiment_verified",
    "repeatedly_verified",
}

VALID_LEARNING_SCOPES = {
    "private",
    "user",
    "public",
}

VALID_LEARNING_EVENT_TYPES = {
    "decision",
    "test_result",
    "user_feedback",
    "validation_report",
    "iteration_plan",
    "hardware_debug",
}

VALID_SUGGESTION_STATUSES = {
    "new",
    "accepted",
    "rejected",
    "later",
    "ignored",
}

VALID_SUGGESTION_CATEGORIES = {
    "scope_drift",
    "unverified_assumption",
    "cost_optimization",
    "tech_risk",
    "test_gap",
    "new_opportunity",
}

VALID_SUGGESTION_PRIORITIES = {
    "low",
    "medium",
    "high",
    "critical",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LearningRecord:
    """A single piece of extracted learning from project history."""

    memory: str
    memory_type: str
    source: str = ""
    source_project_id: str | None = None
    confidence: str = "low"
    verification_status: str = "unverified"
    scope: str = "private"
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"lrn_{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.memory_type and self.memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(f"Invalid memory_type '{self.memory_type}'")
        if self.confidence and self.confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")
        if self.verification_status and self.verification_status not in VALID_VERIFICATION_STATUSES:
            raise ValueError(f"Invalid verification_status '{self.verification_status}'")
        if self.scope and self.scope not in VALID_LEARNING_SCOPES:
            raise ValueError(f"Invalid scope '{self.scope}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory": self.memory,
            "memory_type": self.memory_type,
            "source": self.source,
            "source_project_id": self.source_project_id,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "scope": self.scope,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningRecord":
        return cls(
            id=data.get("id") or f"lrn_{uuid.uuid4().hex[:8]}",
            memory=data.get("memory", ""),
            memory_type=data.get("memory_type", ""),
            source=data.get("source", ""),
            source_project_id=data.get("source_project_id"),
            confidence=data.get("confidence", "low"),
            verification_status=data.get("verification_status", "unverified"),
            scope=data.get("scope", "private"),
            tags=list(data.get("tags") or []),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
        )


@dataclass
class FailureKnowledge:
    """A validated failure pattern extracted from project history."""

    problem: str
    cause: str
    solution: str
    affected_scope: str = ""
    verification: str = ""
    source_project_id: str | None = None
    confidence: str = "low"
    verification_status: str = "unverified"
    id: str = field(default_factory=lambda: f"fail_{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.confidence and self.confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")
        if self.verification_status and self.verification_status not in VALID_VERIFICATION_STATUSES:
            raise ValueError(f"Invalid verification_status '{self.verification_status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "problem": self.problem,
            "cause": self.cause,
            "solution": self.solution,
            "affected_scope": self.affected_scope,
            "verification": self.verification,
            "source_project_id": self.source_project_id,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureKnowledge":
        return cls(
            id=data.get("id") or f"fail_{uuid.uuid4().hex[:8]}",
            problem=data.get("problem", ""),
            cause=data.get("cause", ""),
            solution=data.get("solution", ""),
            affected_scope=data.get("affected_scope", ""),
            verification=data.get("verification", ""),
            source_project_id=data.get("source_project_id"),
            confidence=data.get("confidence", "low"),
            verification_status=data.get("verification_status", "unverified"),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
        )


@dataclass
class SuccessKnowledge:
    """A validated success pattern extracted from project history."""

    goal: str
    solution: str
    conditions: list[str] = field(default_factory=list)
    result: str = ""
    source_project_id: str | None = None
    confidence: str = "low"
    verification_status: str = "unverified"
    id: str = field(default_factory=lambda: f"succ_{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.confidence and self.confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")
        if self.verification_status and self.verification_status not in VALID_VERIFICATION_STATUSES:
            raise ValueError(f"Invalid verification_status '{self.verification_status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "solution": self.solution,
            "conditions": list(self.conditions),
            "result": self.result,
            "source_project_id": self.source_project_id,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SuccessKnowledge":
        return cls(
            id=data.get("id") or f"succ_{uuid.uuid4().hex[:8]}",
            goal=data.get("goal", ""),
            solution=data.get("solution", ""),
            conditions=list(data.get("conditions") or []),
            result=data.get("result", ""),
            source_project_id=data.get("source_project_id"),
            confidence=data.get("confidence", "low"),
            verification_status=data.get("verification_status", "unverified"),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
        )


@dataclass
class Suggestion:
    """A proactive improvement suggestion generated for a project."""

    suggestion: str
    reason: str
    source_project_id: str
    evidence: list[str] = field(default_factory=list)
    impact: str = ""
    priority: str = "medium"
    status: str = "new"
    category: str = ""
    related_learning_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"sug_{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.priority and self.priority not in VALID_SUGGESTION_PRIORITIES:
            raise ValueError(f"Invalid priority '{self.priority}'")
        if self.status and self.status not in VALID_SUGGESTION_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'")
        if self.category and self.category not in VALID_SUGGESTION_CATEGORIES:
            raise ValueError(f"Invalid category '{self.category}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "suggestion": self.suggestion,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "impact": self.impact,
            "priority": self.priority,
            "status": self.status,
            "category": self.category,
            "source_project_id": self.source_project_id,
            "related_learning_ids": list(self.related_learning_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Suggestion":
        return cls(
            id=data.get("id") or f"sug_{uuid.uuid4().hex[:8]}",
            suggestion=data.get("suggestion", ""),
            reason=data.get("reason", ""),
            evidence=list(data.get("evidence") or []),
            impact=data.get("impact", ""),
            priority=data.get("priority", "medium"),
            status=data.get("status", "new"),
            category=data.get("category", ""),
            source_project_id=data.get("source_project_id", ""),
            related_learning_ids=list(data.get("related_learning_ids") or []),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
        )


@dataclass
class LearningEvent:
    """An event that may trigger learning extraction."""

    event_type: str
    project_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    artifact_id: str | None = None
    timestamp: str = field(default_factory=_now)
    id: str = field(default_factory=lambda: f"lev_{uuid.uuid4().hex[:8]}")

    def __post_init__(self) -> None:
        if self.event_type and self.event_type not in VALID_LEARNING_EVENT_TYPES:
            raise ValueError(f"Invalid event_type '{self.event_type}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "project_id": self.project_id,
            "artifact_id": self.artifact_id,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningEvent":
        return cls(
            id=data.get("id") or f"lev_{uuid.uuid4().hex[:8]}",
            event_type=data.get("event_type", ""),
            project_id=data.get("project_id", ""),
            artifact_id=data.get("artifact_id"),
            payload=dict(data.get("payload") or {}),
            timestamp=data.get("timestamp", _now()),
        )


@dataclass
class LearningArtifactBundle:
    """Bundle of all Phase 9 artifacts for easy serialization."""

    records: list[LearningRecord] = field(default_factory=list)
    failures: list[FailureKnowledge] = field(default_factory=list)
    successes: list[SuccessKnowledge] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "failures": [f.to_dict() for f in self.failures],
            "successes": [s.to_dict() for s in self.successes],
            "suggestions": [s.to_dict() for s in self.suggestions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningArtifactBundle":
        return cls(
            records=[LearningRecord.from_dict(r) for r in data.get("records") or []],
            failures=[FailureKnowledge.from_dict(f) for f in data.get("failures") or []],
            successes=[SuccessKnowledge.from_dict(s) for s in data.get("successes") or []],
            suggestions=[Suggestion.from_dict(s) for s in data.get("suggestions") or []],
        )
