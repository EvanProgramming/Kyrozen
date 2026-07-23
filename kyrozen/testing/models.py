"""Data models for Kyrozen Phase 8 Testing, Validation and Iteration Loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_TEST_TYPES = {
    "functional",
    "ui",
    "api",
    "performance",
    "security",
    "hardware_compile",
    "hardware_module",
    "hardware_integration",
    "hardware_power",
    "hardware_stability",
}

VALID_TEST_STATUSES = {
    "draft",
    "ready",
    "skipped",
    "deprecated",
}

VALID_RESULT_STATUSES = {
    "passed",
    "failed",
    "skipped",
    "error",
}

VALID_FEEDBACK_SOURCES = {
    "interview",
    "trial",
    "survey",
    "comparison",
}

VALID_SENTIMENTS = {
    "positive",
    "neutral",
    "negative",
}

VALID_ITERATION_CATEGORIES = {
    "keep",
    "modify",
    "remove",
    "investigate",
    "new_feature",
}

VALID_VALIDATION_CONCLUSIONS = {
    "pass",
    "fail",
    "partial",
    "insufficient_evidence",
}

VALID_PRIORITIES = {
    "low",
    "medium",
    "high",
    "critical",
}

VALID_TEST_PLAN_STATUSES = {
    "draft",
    "ready",
    "running",
    "completed",
}


@dataclass
class TestCase:
    """One test case derived from a product requirement."""

    id: str = ""                      # e.g. "TC-SW-01"
    name: str = ""
    type: str = ""                    # one of VALID_TEST_TYPES
    related_requirement: str = ""     # PRD requirement text or R{N} reference
    related_feature: str = ""         # Feature name
    description: str = ""
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    environment: str = ""
    priority: str = "medium"          # one of VALID_PRIORITIES
    status: str = "draft"             # one of VALID_TEST_STATUSES

    def __post_init__(self) -> None:
        if self.type and self.type not in VALID_TEST_TYPES:
            raise ValueError(f"Invalid test type '{self.type}'")
        if self.priority and self.priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority '{self.priority}'")
        if self.status and self.status not in VALID_TEST_STATUSES:
            raise ValueError(f"Invalid test status '{self.status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "related_requirement": self.related_requirement,
            "related_feature": self.related_feature,
            "description": self.description,
            "steps": list(self.steps),
            "expected": self.expected,
            "environment": self.environment,
            "priority": self.priority,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestCase":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            type=data.get("type", ""),
            related_requirement=data.get("related_requirement", ""),
            related_feature=data.get("related_feature", ""),
            description=data.get("description", ""),
            steps=list(data.get("steps") or []),
            expected=data.get("expected", ""),
            environment=data.get("environment", ""),
            priority=data.get("priority", "medium"),
            status=data.get("status", "draft"),
        )


@dataclass
class TestResult:
    """Execution result for a single test case."""

    test_case_id: str = ""
    test_case_name: str = ""
    result: str = ""                  # one of VALID_RESULT_STATUSES
    actual: str = ""
    errors: str = ""
    stdout: str = ""
    stderr: str = ""
    timestamp: str = ""
    duration_ms: int = 0
    environment: str = ""
    executed_by: str = "agent"        # agent | user | ci

    def __post_init__(self) -> None:
        if self.result and self.result not in VALID_RESULT_STATUSES:
            raise ValueError(f"Invalid result status '{self.result}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "test_case_name": self.test_case_name,
            "result": self.result,
            "actual": self.actual,
            "errors": self.errors,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "environment": self.environment,
            "executed_by": self.executed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestResult":
        return cls(
            test_case_id=data.get("test_case_id", ""),
            test_case_name=data.get("test_case_name", ""),
            result=data.get("result", ""),
            actual=data.get("actual", ""),
            errors=data.get("errors", ""),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            timestamp=data.get("timestamp", ""),
            duration_ms=int(data.get("duration_ms", 0) or 0),
            environment=data.get("environment", ""),
            executed_by=data.get("executed_by", "agent"),
        )


@dataclass
class TestPlan:
    """Collection of test cases tied to product requirements."""

    name: str = ""
    objective: str = ""
    requirements: list[str] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    success_criteria: str = ""
    environment: str = ""
    status: str = "draft"             # one of VALID_TEST_PLAN_STATUSES

    def __post_init__(self) -> None:
        if self.status and self.status not in VALID_TEST_PLAN_STATUSES:
            raise ValueError(f"Invalid test plan status '{self.status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "objective": self.objective,
            "requirements": list(self.requirements),
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "success_criteria": self.success_criteria,
            "environment": self.environment,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestPlan":
        return cls(
            name=data.get("name", ""),
            objective=data.get("objective", ""),
            requirements=list(data.get("requirements") or []),
            test_cases=[TestCase.from_dict(tc) for tc in data.get("test_cases") or []],
            success_criteria=data.get("success_criteria", ""),
            environment=data.get("environment", ""),
            status=data.get("status", "draft"),
        )


@dataclass
class UserFeedback:
    """One piece of user validation feedback."""

    source_type: str = ""             # one of VALID_FEEDBACK_SOURCES
    content: str = ""
    problems: list[str] = field(default_factory=list)
    sentiment: str = ""               # one of VALID_SENTIMENTS
    timestamp: str = ""
    participant_id: str = ""

    def __post_init__(self) -> None:
        if self.source_type and self.source_type not in VALID_FEEDBACK_SOURCES:
            raise ValueError(f"Invalid feedback source type '{self.source_type}'")
        if self.sentiment and self.sentiment not in VALID_SENTIMENTS:
            raise ValueError(f"Invalid sentiment '{self.sentiment}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "content": self.content,
            "problems": list(self.problems),
            "sentiment": self.sentiment,
            "timestamp": self.timestamp,
            "participant_id": self.participant_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserFeedback":
        return cls(
            source_type=data.get("source_type", ""),
            content=data.get("content", ""),
            problems=list(data.get("problems") or []),
            sentiment=data.get("sentiment", ""),
            timestamp=data.get("timestamp", ""),
            participant_id=data.get("participant_id", ""),
        )


@dataclass
class IterationItem:
    """One recommendation for the next iteration."""

    category: str = ""                # one of VALID_ITERATION_CATEGORIES
    target: str = ""
    reason: str = ""
    priority: str = "medium"          # one of VALID_PRIORITIES

    def __post_init__(self) -> None:
        if self.category and self.category not in VALID_ITERATION_CATEGORIES:
            raise ValueError(f"Invalid iteration category '{self.category}'")
        if self.priority and self.priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority '{self.priority}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "target": self.target,
            "reason": self.reason,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IterationItem":
        return cls(
            category=data.get("category", ""),
            target=data.get("target", ""),
            reason=data.get("reason", ""),
            priority=data.get("priority", "medium"),
        )


@dataclass
class IterationPlan:
    """Plan of what to keep, modify, remove, investigate, or add next."""

    items: list[IterationItem] = field(default_factory=list)
    overall_recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "overall_recommendation": self.overall_recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IterationPlan":
        return cls(
            items=[IterationItem.from_dict(item) for item in data.get("items") or []],
            overall_recommendation=data.get("overall_recommendation", ""),
        )


@dataclass
class ValidationReport:
    """Product validation report combining engineering tests and user feedback."""

    original_problem: str = ""
    tested_solution: str = ""
    test_results_summary: dict[str, Any] = field(default_factory=dict)
    user_feedback: list[UserFeedback] = field(default_factory=list)
    success_metrics: str = ""
    conclusion: str = ""              # one of VALID_VALIDATION_CONCLUSIONS
    next_iteration: list[IterationItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.conclusion and self.conclusion not in VALID_VALIDATION_CONCLUSIONS:
            raise ValueError(f"Invalid validation conclusion '{self.conclusion}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_problem": self.original_problem,
            "tested_solution": self.tested_solution,
            "test_results_summary": dict(self.test_results_summary),
            "user_feedback": [fb.to_dict() for fb in self.user_feedback],
            "success_metrics": self.success_metrics,
            "conclusion": self.conclusion,
            "next_iteration": [item.to_dict() for item in self.next_iteration],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationReport":
        return cls(
            original_problem=data.get("original_problem", ""),
            tested_solution=data.get("tested_solution", ""),
            test_results_summary=dict(data.get("test_results_summary") or {}),
            user_feedback=[UserFeedback.from_dict(fb) for fb in data.get("user_feedback") or []],
            success_metrics=data.get("success_metrics", ""),
            conclusion=data.get("conclusion", ""),
            next_iteration=[IterationItem.from_dict(item) for item in data.get("next_iteration") or []],
        )


@dataclass
class TestingArtifactBundle:
    """Bundle of all Phase 8 artifacts for easy serialization."""

    __test__ = False  # Not a pytest test class

    test_plan: TestPlan = field(default_factory=TestPlan)
    test_results: list[TestResult] = field(default_factory=list)
    validation_report: ValidationReport = field(default_factory=ValidationReport)
    iteration_plan: IterationPlan = field(default_factory=IterationPlan)
    user_feedback: list[UserFeedback] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_plan": self.test_plan.to_dict(),
            "test_results": [r.to_dict() for r in self.test_results],
            "validation_report": self.validation_report.to_dict(),
            "iteration_plan": self.iteration_plan.to_dict(),
            "user_feedback": [fb.to_dict() for fb in self.user_feedback],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestingArtifactBundle":
        return cls(
            test_plan=TestPlan.from_dict(data.get("test_plan") or {}),
            test_results=[TestResult.from_dict(r) for r in data.get("test_results") or []],
            validation_report=ValidationReport.from_dict(data.get("validation_report") or {}),
            iteration_plan=IterationPlan.from_dict(data.get("iteration_plan") or {}),
            user_feedback=[UserFeedback.from_dict(fb) for fb in data.get("user_feedback") or []],
        )
