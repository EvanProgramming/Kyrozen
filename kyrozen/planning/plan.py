"""Data model for explicit, file-backed execution plans.

Each Kyrozen agent (problem discovery, market research, planning, development,
etc.) is expected to write a real ``.kyrozen/PLAN.json`` *before* starting work.
The plan is not a cosmetic bullet list -- it is the contract the agent follows
through the rest of the stage.  Steps can be marked ``in_progress`` /
``completed`` / ``failed`` as work progresses, and the desktop UI reads the
file directly to render the task panel.

P0-R6: real planning, not visual filler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PLAN_STEP_STATUSES = {"pending", "in_progress", "completed", "failed"}
_PLAN_STAGES = (
    "problem_discovery",
    "market_research",
    "product_definition",
    "solution_design",
    "development",
    "testing",
    "iteration",
)


@dataclass
class PlanStep:
    """One concrete step the agent intends to perform."""

    id: str
    title: str
    detail: str = ""
    status: str = "pending"

    def __post_init__(self) -> None:
        if self.status not in PLAN_STEP_STATUSES:
            raise ValueError(
                f"Invalid plan step status '{self.status}'. "
                f"Expected one of {sorted(PLAN_STEP_STATUSES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanStep":
        return cls(
            id=str(data.get("id") or "").strip() or "step",
            title=str(data.get("title") or "").strip(),
            detail=str(data.get("detail") or ""),
            status=str(data.get("status") or "pending"),
        )


@dataclass
class ExecutionPlan:
    """Structured plan for the current stage of a project."""

    stage: str = ""
    title: str = ""
    goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    task_id: str = ""

    def __post_init__(self) -> None:
        if self.stage and self.stage not in _PLAN_STAGES:
            raise ValueError(
                f"Unknown plan stage '{self.stage}'. "
                f"Expected one of {list(_PLAN_STAGES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "title": self.title,
            "goal": self.goal,
            "task_id": self.task_id,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionPlan":
        return cls(
            stage=str(data.get("stage") or ""),
            title=str(data.get("title") or ""),
            goal=str(data.get("goal") or ""),
            task_id=str(data.get("task_id") or ""),
            steps=[PlanStep.from_dict(step) for step in (data.get("steps") or [])],
        )

    def mark_step(self, step_id: str, status: str) -> bool:
        """Update one step's status.  Returns True if the step was found."""
        for step in self.steps:
            if step.id == step_id:
                if status not in PLAN_STEP_STATUSES:
                    raise ValueError(f"Invalid status '{status}'")
                step.status = status
                return True
        return False