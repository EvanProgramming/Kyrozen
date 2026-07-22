"""Data models for Kyrozen Phase 6 Software Development.

These models capture the technical plan, feature-to-code traceability,
test reports, and deployment guides produced during software development.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_APPLICATION_TYPES = {
    "web_app",
    "website",
    "simple_saas",
    "ai_tool",
    "automation_tool",
    "desktop_app",
    "cli_tool",
}

VALID_FEATURE_STATUSES = {
    "pending",
    "implemented",
    "tested",
    "failed",
}

VALID_DEVELOPMENT_STAGES = {
    "understanding_inputs",
    "technical_planning",
    "project_initializing",
    "implementing",
    "testing",
    "debugging",
    "completed",
    "failed",
}

DEVELOPMENT_DECISIONS = {
    "continue_development",
    "change_stack",
    "narrow_scope",
    "pause",
    "abandon",
}


@dataclass
class TechnicalPlan:
    """Technical implementation plan derived from PRD."""

    application_type: str = ""  # e.g. web_app, website, ai_tool
    architecture: str = ""
    frontend: str = ""
    backend: str = ""
    database: str = ""
    apis: str = ""
    deployment: str = ""
    dependencies: list[str] = field(default_factory=list)
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.application_type and self.application_type not in VALID_APPLICATION_TYPES:
            raise ValueError(f"Invalid application_type '{self.application_type}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "application_type": self.application_type,
            "architecture": self.architecture,
            "frontend": self.frontend,
            "backend": self.backend,
            "database": self.database,
            "apis": self.apis,
            "deployment": self.deployment,
            "dependencies": list(self.dependencies),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TechnicalPlan":
        return cls(
            application_type=data.get("application_type", ""),
            architecture=data.get("architecture", ""),
            frontend=data.get("frontend", ""),
            backend=data.get("backend", ""),
            database=data.get("database", ""),
            apis=data.get("apis", ""),
            deployment=data.get("deployment", ""),
            dependencies=list(data.get("dependencies") or []),
            rationale=data.get("rationale", ""),
        )


@dataclass
class FeatureImplementation:
    """Traceability record linking a PRD feature to code and tests."""

    prd_feature: str = ""
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    status: str = "pending"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in VALID_FEATURE_STATUSES:
            raise ValueError(f"Invalid feature status '{self.status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "prd_feature": self.prd_feature,
            "files": list(self.files),
            "tests": list(self.tests),
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureImplementation":
        return cls(
            prd_feature=data.get("prd_feature", ""),
            files=list(data.get("files") or []),
            tests=list(data.get("tests") or []),
            status=data.get("status", "pending"),
            notes=data.get("notes", ""),
        )


@dataclass
class TestReport:
    """Aggregated test results for the software project."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    fix_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "fix_history": list(self.fix_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestReport":
        return cls(
            total=int(data.get("total", 0) or 0),
            passed=int(data.get("passed", 0) or 0),
            failed=int(data.get("failed", 0) or 0),
            skipped=int(data.get("skipped", 0) or 0),
            errors=list(data.get("errors") or []),
            fix_history=list(data.get("fix_history") or []),
        )


@dataclass
class DeploymentGuide:
    """Instructions for running and deploying the prototype."""

    run_instructions: str = ""
    deployment_instructions: str = ""
    requirements: list[str] = field(default_factory=list)
    environment_variables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_instructions": self.run_instructions,
            "deployment_instructions": self.deployment_instructions,
            "requirements": list(self.requirements),
            "environment_variables": list(self.environment_variables),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeploymentGuide":
        return cls(
            run_instructions=data.get("run_instructions", ""),
            deployment_instructions=data.get("deployment_instructions", ""),
            requirements=list(data.get("requirements") or []),
            environment_variables=list(data.get("environment_variables") or []),
        )


@dataclass
class DevelopmentArtifactBundle:
    """Bundle of all Phase 6 artifacts for easy serialization."""

    technical_plan: TechnicalPlan = field(default_factory=TechnicalPlan)
    feature_records: list[FeatureImplementation] = field(default_factory=list)
    test_report: TestReport = field(default_factory=TestReport)
    deployment_guide: DeploymentGuide = field(default_factory=DeploymentGuide)

    def to_dict(self) -> dict[str, Any]:
        return {
            "technical_plan": self.technical_plan.to_dict(),
            "feature_records": [r.to_dict() for r in self.feature_records],
            "test_report": self.test_report.to_dict(),
            "deployment_guide": self.deployment_guide.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DevelopmentArtifactBundle":
        return cls(
            technical_plan=TechnicalPlan.from_dict(data.get("technical_plan") or {}),
            feature_records=[
                FeatureImplementation.from_dict(r)
                for r in data.get("feature_records") or []
            ],
            test_report=TestReport.from_dict(data.get("test_report") or {}),
            deployment_guide=DeploymentGuide.from_dict(data.get("deployment_guide") or {}),
        )
