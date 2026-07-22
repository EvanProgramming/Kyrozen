"""Project entity models for Kyrozen Phase 2."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


PROJECT_STATUSES = {"active", "paused", "completed", "archived"}

PROJECT_STAGES = {
    "problem_discovery",
    "market_research",
    "product_definition",
    "solution_design",
    "development",
    "testing",
    "iteration",
}


@dataclass
class Project:
    """A Kyrozen project workspace."""

    name: str
    description: str = ""
    goal: str = ""
    status: str = "active"
    current_stage: str = "problem_discovery"
    next_steps: str = ""
    blocked_reason: str = ""
    progress: int = 0
    risks: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"proj_{uuid.uuid4().hex[:8]}")
    user_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.status not in PROJECT_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Valid: {PROJECT_STATUSES}")
        if self.current_stage not in PROJECT_STAGES:
            raise ValueError(f"Invalid stage '{self.current_stage}'. Valid: {PROJECT_STAGES}")

    def update(self, **kwargs: Any) -> None:
        """Update project fields and refresh updated_at."""
        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise ValueError(f"Project has no field '{key}'")
            setattr(self, key, value)
        if "status" in kwargs and kwargs["status"] not in PROJECT_STATUSES:
            raise ValueError(f"Invalid status '{kwargs['status']}'")
        if "current_stage" in kwargs and kwargs["current_stage"] not in PROJECT_STAGES:
            raise ValueError(f"Invalid stage '{kwargs['current_stage']}'")
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "goal": self.goal,
            "status": self.status,
            "current_stage": self.current_stage,
            "next_steps": self.next_steps,
            "blocked_reason": self.blocked_reason,
            "progress": self.progress,
            "risks": self.risks,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        return cls(
            id=data.get("id") or f"proj_{uuid.uuid4().hex[:8]}",
            user_id=data.get("user_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            goal=data.get("goal", ""),
            status=data.get("status", "active"),
            current_stage=data.get("current_stage", "problem_discovery"),
            next_steps=data.get("next_steps", ""),
            blocked_reason=data.get("blocked_reason", ""),
            progress=data.get("progress", 0),
            risks=data.get("risks", []),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class Decision:
    """A recorded decision within a project."""

    project_id: str
    decision: str
    reason: str = ""
    alternatives: list[str] = field(default_factory=list)
    rejected_reasons: dict[str, str] = field(default_factory=dict)
    source: str = "agent"
    id: str = field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "decision": self.decision,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "rejected_reasons": self.rejected_reasons,
            "source": self.source,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        return cls(
            id=data.get("id") or f"dec_{uuid.uuid4().hex[:8]}",
            project_id=data.get("project_id", ""),
            decision=data.get("decision", ""),
            reason=data.get("reason", ""),
            alternatives=data.get("alternatives", []),
            rejected_reasons=data.get("rejected_reasons", {}),
            source=data.get("source", "agent"),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class Artifact:
    """A project artifact with versioning."""

    project_id: str
    type: str
    title: str
    content: str = ""
    version: int = 1
    change_reason: str = ""
    id: str = field(default_factory=lambda: f"art_{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def bump_version(self, new_content: str, change_reason: str = "") -> "Artifact":
        """Create a new version of this artifact."""
        return Artifact(
            project_id=self.project_id,
            type=self.type,
            title=self.title,
            content=new_content,
            version=self.version + 1,
            change_reason=change_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "version": self.version,
            "change_reason": self.change_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(
            id=data.get("id") or f"art_{uuid.uuid4().hex[:8]}",
            project_id=data.get("project_id", ""),
            type=data.get("type", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            version=data.get("version", 1),
            change_reason=data.get("change_reason", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
