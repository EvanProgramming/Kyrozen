"""State management for Kyrozen Phase 9 Learning sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    FailureKnowledge,
    LearningEvent,
    LearningRecord,
    Suggestion,
    SuccessKnowledge,
)


VALID_LEARNING_STAGES = {
    "idle",
    "extracting",
    "analyzing",
    "suggesting",
    "reviewing",
    "completed",
    "failed",
}


@dataclass
class LearningSession:
    """Tracks the state of one learning and proactive improvement conversation."""

    project_id: str
    stage: str = "idle"
    records: list[LearningRecord] = field(default_factory=list)
    failures: list[FailureKnowledge] = field(default_factory=list)
    successes: list[SuccessKnowledge] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    events: list[LearningEvent] = field(default_factory=list)
    idle_analysis_enabled: bool = True
    logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage and self.stage not in VALID_LEARNING_STAGES:
            raise ValueError(f"Invalid learning stage '{self.stage}'")

    def set_stage(self, stage: str) -> None:
        if stage not in VALID_LEARNING_STAGES:
            raise ValueError(f"Invalid learning stage '{stage}'")
        self.stage = stage
        self.logs.append(f"Stage: {stage}")

    def add_record(self, record: LearningRecord) -> None:
        self.records.append(record)
        self.logs.append(f"Learning record added: {record.id} ({record.memory_type})")

    def add_failure(self, failure: FailureKnowledge) -> None:
        self.failures.append(failure)
        self.logs.append(f"Failure knowledge added: {failure.id}")

    def add_success(self, success: SuccessKnowledge) -> None:
        self.successes.append(success)
        self.logs.append(f"Success knowledge added: {success.id}")

    def add_suggestion(self, suggestion: Suggestion) -> None:
        self.suggestions.append(suggestion)
        self.logs.append(f"Suggestion added: {suggestion.id} ({suggestion.category})")

    def update_suggestion_status(self, suggestion_id: str, status: str) -> bool:
        for suggestion in self.suggestions:
            if suggestion.id == suggestion_id:
                suggestion.status = status
                self.logs.append(f"Suggestion {suggestion_id} status -> {status}")
                return True
        return False

    def add_event(self, event: LearningEvent) -> None:
        self.events.append(event)
        self.logs.append(f"Learning event added: {event.id} ({event.event_type})")

    def toggle_idle_analysis(self, enabled: bool) -> None:
        self.idle_analysis_enabled = enabled
        self.logs.append(f"Idle analysis {'enabled' if enabled else 'disabled'}")

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for record in self.records:
            by_type[record.memory_type] = by_type.get(record.memory_type, 0) + 1
        by_status: dict[str, int] = {}
        for suggestion in self.suggestions:
            by_status[suggestion.status] = by_status.get(suggestion.status, 0) + 1
        return {
            "stage": self.stage,
            "record_count": len(self.records),
            "failure_count": len(self.failures),
            "success_count": len(self.successes),
            "suggestion_count": len(self.suggestions),
            "event_count": len(self.events),
            "record_types": by_type,
            "suggestion_statuses": by_status,
            "idle_analysis_enabled": self.idle_analysis_enabled,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "records": [r.to_dict() for r in self.records],
            "failures": [f.to_dict() for f in self.failures],
            "successes": [s.to_dict() for s in self.successes],
            "suggestions": [s.to_dict() for s in self.suggestions],
            "events": [e.to_dict() for e in self.events],
            "idle_analysis_enabled": self.idle_analysis_enabled,
            "logs": list(self.logs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningSession":
        session = cls(
            project_id=data.get("project_id", ""),
            stage=data.get("stage", "idle"),
            records=[LearningRecord.from_dict(r) for r in data.get("records") or []],
            failures=[FailureKnowledge.from_dict(f) for f in data.get("failures") or []],
            successes=[SuccessKnowledge.from_dict(s) for s in data.get("successes") or []],
            suggestions=[Suggestion.from_dict(s) for s in data.get("suggestions") or []],
            events=[LearningEvent.from_dict(e) for e in data.get("events") or []],
            idle_analysis_enabled=data.get("idle_analysis_enabled", True),
            logs=list(data.get("logs") or []),
        )
        return session
