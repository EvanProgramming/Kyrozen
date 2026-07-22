"""Runtime state for Software Development sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    VALID_DEVELOPMENT_STAGES,
    DeploymentGuide,
    DevelopmentArtifactBundle,
    FeatureImplementation,
    TechnicalPlan,
    TestReport,
)


@dataclass
class DevelopmentSession:
    """Tracks the state of one software development conversation."""

    project_id: str
    stage: str = "understanding_inputs"
    technical_plan: TechnicalPlan = field(default_factory=TechnicalPlan)
    feature_records: list[FeatureImplementation] = field(default_factory=list)
    test_report: TestReport = field(default_factory=TestReport)
    deployment_guide: DeploymentGuide = field(default_factory=DeploymentGuide)
    logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage not in VALID_DEVELOPMENT_STAGES:
            raise ValueError(f"Invalid development stage '{self.stage}'")

    def set_stage(self, stage: str) -> None:
        if stage not in VALID_DEVELOPMENT_STAGES:
            raise ValueError(f"Invalid development stage '{stage}'")
        self.stage = stage
        self.logs.append(f"Stage: {stage}")

    def update_technical_plan(self, plan: TechnicalPlan) -> None:
        self.technical_plan = plan
        self.logs.append("Technical plan updated")

    def add_or_update_feature(self, record: FeatureImplementation) -> None:
        existing = {r.prd_feature.lower() for r in self.feature_records if r.prd_feature}
        if record.prd_feature and record.prd_feature.lower() in existing:
            for i, r in enumerate(self.feature_records):
                if r.prd_feature.lower() == record.prd_feature.lower():
                    self.feature_records[i] = record
                    self.logs.append(f"Feature record updated: {record.prd_feature}")
                    return
        self.feature_records.append(record)
        self.logs.append(f"Feature record added: {record.prd_feature}")

    def update_test_report(self, report: TestReport) -> None:
        self.test_report = report
        self.logs.append("Test report updated")

    def update_deployment_guide(self, guide: DeploymentGuide) -> None:
        self.deployment_guide = guide
        self.logs.append("Deployment guide updated")

    def to_bundle(self) -> DevelopmentArtifactBundle:
        return DevelopmentArtifactBundle(
            technical_plan=self.technical_plan,
            feature_records=list(self.feature_records),
            test_report=self.test_report,
            deployment_guide=self.deployment_guide,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "bundle": self.to_bundle().to_dict(),
            "logs": list(self.logs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DevelopmentSession":
        bundle = DevelopmentArtifactBundle.from_dict(data.get("bundle") or {})
        session = cls(
            project_id=data.get("project_id", ""),
            stage=data.get("stage", "understanding_inputs"),
            technical_plan=bundle.technical_plan,
            feature_records=bundle.feature_records,
            test_report=bundle.test_report,
            deployment_guide=bundle.deployment_guide,
            logs=list(data.get("logs") or []),
        )
        return session
