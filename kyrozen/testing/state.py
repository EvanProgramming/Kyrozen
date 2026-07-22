"""State management for Kyrozen Phase 8 Testing sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    IterationPlan,
    TestCase,
    TestPlan,
    TestResult,
    UserFeedback,
    ValidationReport,
)


VALID_TESTING_STAGES = {
    "understanding_inputs",
    "planning",
    "executing",
    "collecting_feedback",
    "validating",
    "iterating",
    "completed",
    "failed",
}


@dataclass
class TestingSession:
    """Tracks the state of one testing and validation conversation."""

    project_id: str
    stage: str = "understanding_inputs"
    test_plan: TestPlan = field(default_factory=TestPlan)
    test_results: list[TestResult] = field(default_factory=list)
    user_feedback: list[UserFeedback] = field(default_factory=list)
    validation_report: ValidationReport = field(default_factory=ValidationReport)
    iteration_plan: IterationPlan = field(default_factory=IterationPlan)
    logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage and self.stage not in VALID_TESTING_STAGES:
            raise ValueError(f"Invalid testing stage '{self.stage}'")

    def set_stage(self, stage: str) -> None:
        if stage not in VALID_TESTING_STAGES:
            raise ValueError(f"Invalid testing stage '{stage}'")
        self.stage = stage
        self.logs.append(f"Stage: {stage}")

    def update_test_plan(self, plan: TestPlan) -> None:
        self.test_plan = plan
        self.logs.append(f"Test plan updated: {plan.name} ({len(plan.test_cases)} cases)")

    def add_or_update_test_case(self, case: TestCase) -> None:
        """Add a new test case or replace an existing one by id."""
        existing = {c.id: i for i, c in enumerate(self.test_plan.test_cases) if c.id}
        if case.id and case.id in existing:
            self.test_plan.test_cases[existing[case.id]] = case
            self.logs.append(f"Test case updated: {case.id}")
        else:
            if not case.id:
                case.id = f"TC-{len(self.test_plan.test_cases) + 1:03d}"
            self.test_plan.test_cases.append(case)
            self.logs.append(f"Test case added: {case.id}")

    def add_test_result(self, result: TestResult) -> None:
        self.test_results.append(result)
        self.logs.append(f"Test result: {result.test_case_id} -> {result.result}")

    def add_user_feedback(self, feedback: UserFeedback) -> None:
        self.user_feedback.append(feedback)
        self.logs.append(f"User feedback: {feedback.source_type} ({feedback.sentiment})")

    def update_validation_report(self, report: ValidationReport) -> None:
        self.validation_report = report
        self.logs.append(f"Validation report updated: {report.conclusion}")

    def update_iteration_plan(self, plan: IterationPlan) -> None:
        self.iteration_plan = plan
        self.logs.append(f"Iteration plan updated: {len(plan.items)} items")

    def summary(self) -> dict[str, Any]:
        """Return a concise summary of the session."""
        by_status: dict[str, int] = {}
        for r in self.test_results:
            by_status[r.result] = by_status.get(r.result, 0) + 1
        return {
            "stage": self.stage,
            "test_case_count": len(self.test_plan.test_cases),
            "test_result_count": len(self.test_results),
            "result_summary": by_status,
            "feedback_count": len(self.user_feedback),
            "iteration_items": len(self.iteration_plan.items),
            "validation_conclusion": self.validation_report.conclusion,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "test_plan": self.test_plan.to_dict(),
            "test_results": [r.to_dict() for r in self.test_results],
            "user_feedback": [fb.to_dict() for fb in self.user_feedback],
            "validation_report": self.validation_report.to_dict(),
            "iteration_plan": self.iteration_plan.to_dict(),
            "logs": list(self.logs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestingSession":
        session = cls(
            project_id=data.get("project_id", ""),
            stage=data.get("stage", "understanding_inputs"),
            test_plan=TestPlan.from_dict(data.get("test_plan") or {}),
            test_results=[TestResult.from_dict(r) for r in data.get("test_results") or []],
            user_feedback=[UserFeedback.from_dict(fb) for fb in data.get("user_feedback") or []],
            validation_report=ValidationReport.from_dict(data.get("validation_report") or {}),
            iteration_plan=IterationPlan.from_dict(data.get("iteration_plan") or {}),
            logs=list(data.get("logs") or []),
        )
        return session
