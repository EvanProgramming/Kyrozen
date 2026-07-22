"""Tools for software development in Kyrozen Phase 6.

These tools allow the Software Development Agent to persist technical plans,
feature implementation records, test reports, deployment guides, and development
decisions into the project workspace.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from kyrozen.development.models import (
    DEVELOPMENT_DECISIONS,
    DeploymentGuide,
    DevelopmentArtifactBundle,
    FeatureImplementation,
    TechnicalPlan,
    TestReport,
)

from .base import Tool, ToolParameter, ToolResult, ToolSchema

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class SaveTechnicalPlanTool(Tool):
    """Save or update the Technical Plan artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_technical_plan"
        self.description = "Save or update the Technical Plan artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="plan", param_type="object", description="Technical Plan fields as a JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        plan_data = parameters.get("plan", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            plan = TechnicalPlan.from_dict(plan_data)
            content = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="technical_plan",
                title="Technical Plan",
                content=content,
                change_reason="Technical planning update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveFeatureImplementationTool(Tool):
    """Save or update a Feature Implementation Record artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_feature_implementation"
        self.description = "Save or update a Feature Implementation Record linking PRD features to code and tests."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="record", param_type="object", description="FeatureImplementation fields as a JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        record_data = parameters.get("record", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            record = FeatureImplementation.from_dict(record_data)
            content = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="feature_implementation_record",
                title=f"Feature Implementation: {record.prd_feature[:40]}",
                content=content,
                change_reason="Feature implementation update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveTestReportTool(Tool):
    """Save or update the Test Report artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_test_report"
        self.description = "Save or update the Test Report artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="report", param_type="object", description="TestReport fields as a JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        report_data = parameters.get("report", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            report = TestReport.from_dict(report_data)
            content = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="test_report",
                title="Test Report",
                content=content,
                change_reason="Test report update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveDeploymentGuideTool(Tool):
    """Save or update the Deployment Guide artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_deployment_guide"
        self.description = "Save or update the Deployment Guide artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="guide", param_type="object", description="DeploymentGuide fields as a JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        guide_data = parameters.get("guide", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            guide = DeploymentGuide.from_dict(guide_data)
            content = json.dumps(guide.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="deployment_guide",
                title="Deployment Guide",
                content=content,
                change_reason="Deployment guide update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class RecordDevelopmentDecisionTool(Tool):
    """Record a major development decision in the project workspace."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_development_decision"
        self.description = "Record a development decision, the reason, and rejected alternatives."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="decision", param_type="string", description=f"Decision: one of {', '.join(sorted(DEVELOPMENT_DECISIONS))}"),
                    ToolParameter(name="reason", param_type="string", description="Why this decision was made"),
                    ToolParameter(name="alternatives", param_type="array", description="List of alternative options considered", required=False),
                    ToolParameter(name="rejected_reasons", param_type="object", description="Mapping from rejected alternative to reason", required=False),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        decision = parameters.get("decision", "")
        reason = parameters.get("reason", "")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        if decision not in DEVELOPMENT_DECISIONS:
            return ToolResult(
                success=False,
                data=None,
                error=f"Invalid decision '{decision}'. Valid: {', '.join(sorted(DEVELOPMENT_DECISIONS))}",
            )
        try:
            dec = self.project_manager.add_decision(
                project_id=project_id,
                decision=f"Development decision: {decision}",
                reason=reason,
                alternatives=list(parameters.get("alternatives") or []),
                rejected_reasons=dict(parameters.get("rejected_reasons") or {}),
                source="agent",
            )
            return ToolResult(success=True, data={"decision_id": dec.id, "decision": decision})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
