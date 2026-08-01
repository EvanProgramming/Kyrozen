"""Tools for software development in Kyrozen Phase 6.

These tools allow the Software Development Agent to persist technical plans,
feature implementation records, test reports, deployment guides, and development
decisions into the project workspace.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.development.models import (
    Changelog,
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
    """Save or update the Technical Plan artifact for a project.

    In addition to persisting the plan to the project artifact store (when a
    project manager is available), this tool ALWAYS writes a real
    ``docs/TECH_DESIGN.md`` file into the workspace. The solution_design stage
    gate detects the technical design by scanning for that file; without it the
    gate can never advance, so the file write is mandatory regardless of whether
    the cloud artifact store is reachable.
    """

    def __init__(self, project_manager: "ProjectManager | None" = None, config: Any = None) -> None:
        self.project_manager = project_manager
        self.config = config
        self.name = "save_technical_plan"
        self.description = "Save or update the Technical Plan and write it to docs/TECH_DESIGN.md."
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

    @staticmethod
    def _resolve_workspace(project_id, project_manager, config):
        if project_manager is not None and project_id and hasattr(config, "project_dir"):
            try:
                return str(config.project_dir(project_id))
            except Exception:
                pass
        ws = getattr(config, "workspace_root", None)
        if ws and Path(ws).is_absolute():
            return str(ws)
        return None

    @staticmethod
    def _render_markdown(plan) -> str:
        d = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        lines = ["# Technical Design (技术方案)", ""]

        def block(title, value):
            lines.append("## " + title)
            lines.append("")
            if isinstance(value, (list, dict)):
                if value:
                    lines.append("```json")
                    lines.append(json.dumps(value, ensure_ascii=False, indent=2))
                    lines.append("```")
                else:
                    lines.append("(无)")
            else:
                lines.append(str(value) if value not in (None, "") else "(无)")
            lines.append("")

        block("应用类型 Application Type", d.get("application_type", ""))
        block("架构 Architecture", d.get("architecture", ""))
        block("前端 Frontend", d.get("frontend", ""))
        block("后端 Backend", d.get("backend", ""))
        block("数据库 Database", d.get("database", ""))
        block("接口 APIs", d.get("apis", ""))
        block("部署 Deployment", d.get("deployment", ""))
        block("依赖 Dependencies", d.get("dependencies", []))
        block("决策依据 Rationale", d.get("rationale", ""))
        return chr(10).join(lines)

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        project_id = parameters.get("project_id")
        plan_data = parameters.get("plan", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            plan = TechnicalPlan.from_dict(plan_data)
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
        result: dict[str, Any] = {}
        # Best-effort artifact persistence (not required on the desktop).
        if self.project_manager is not None:
            try:
                content = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
                artifact = self.project_manager.save_artifact(
                    project_id=project_id,
                    type="technical_plan",
                    title="Technical Plan",
                    content=content,
                    change_reason="Technical planning update",
                )
                result["artifact_id"] = artifact.id
                result["version"] = artifact.version
            except Exception:
                pass
        # MANDATORY: write the real docs/TECH_DESIGN.md deliverable so the gate detects it.
        workspace = self._resolve_workspace(project_id, self.project_manager, self.config)
        if workspace:
            try:
                out = Path(workspace) / "docs" / "TECH_DESIGN.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(self._render_markdown(plan), encoding="utf-8")
                result["file"] = str(out)
            except Exception:
                pass
        if not result:
            return ToolResult(
                success=False,
                data=None,
                error="无法保存技术方案：未找到可写的项目工作区，且项目管理器不可用。",
            )
        # Detect the deliverable. User acceptance is a separate, explicit gate.
        if workspace and result.get("file"):
            try:
                from kyrozen.core.stagegate import record_report_deliverable

                record_report_deliverable(workspace, "tech_design", "design_confirmed")
            except Exception:
                pass
        return ToolResult(success=True, data=result)


class SaveChangelogTool(Tool):
    """Save or update the iteration Changelog and write it to CHANGELOG.md.

    In addition to persisting the changelog to the project artifact store (when a
    project manager is available), this tool ALWAYS writes a real ``CHANGELOG.md``
    file into the workspace root. The iteration stage gate detects the changelog
    by scanning for that file; without it the gate's changelog item can never be
    satisfied, so the file write is mandatory regardless of whether the cloud
    artifact store is reachable.
    """

    def __init__(self, project_manager: "ProjectManager | None" = None, config: Any = None) -> None:
        self.project_manager = project_manager
        self.config = config
        self.name = "save_changelog"
        self.description = "Save or update the iteration Changelog and write it to CHANGELOG.md."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(
                        name="changelog",
                        param_type="object",
                        description="Changelog fields as a JSON object (version, date, summary, entries)",
                    ),
                    ToolParameter(
                        name="content",
                        param_type="string",
                        description="Optional raw markdown; if provided it is written verbatim instead of rendering from `changelog`.",
                        required=False,
                    ),
                ]
            },
        )

    @staticmethod
    def _resolve_workspace(project_id, project_manager, config):
        if project_manager is not None and project_id and hasattr(config, "project_dir"):
            try:
                return str(config.project_dir(project_id))
            except Exception:
                pass
        ws = getattr(config, "workspace_root", None)
        if ws and Path(ws).is_absolute():
            return str(ws)
        return None

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        project_id = parameters.get("project_id")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        content = parameters.get("content")
        changelog_obj = None
        if content is None:
            changelog_data = parameters.get("changelog", {})
            try:
                changelog_obj = Changelog.from_dict(changelog_data)
            except ValueError as e:
                return ToolResult(success=False, data=None, error=str(e))
            content = changelog_obj.to_markdown()
        if not content:
            return ToolResult(success=False, data=None, error="Missing changelog content")
        result: dict[str, Any] = {}
        # Best-effort artifact persistence (not required on the desktop).
        if self.project_manager is not None and changelog_obj is not None:
            try:
                artifact_content = json.dumps(changelog_obj.to_dict(), ensure_ascii=False, indent=2)
                artifact = self.project_manager.save_artifact(
                    project_id=project_id,
                    type="changelog",
                    title="Changelog",
                    content=artifact_content,
                    change_reason="Changelog update",
                )
                result["artifact_id"] = artifact.id
                result["version"] = artifact.version
            except Exception:
                pass
        # MANDATORY: write the real CHANGELOG.md deliverable so the gate detects it.
        workspace = self._resolve_workspace(project_id, self.project_manager, self.config)
        if workspace:
            try:
                out = Path(workspace) / "CHANGELOG.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(content, encoding="utf-8")
                result["file"] = str(out)
            except Exception:
                pass
        if not result:
            return ToolResult(
                success=False,
                data=None,
                error="无法保存变更记录：未找到可写的项目工作区，且项目管理器不可用。",
            )
        # Detect the deliverable. User acceptance is a separate, explicit gate.
        if workspace and result.get("file"):
            try:
                from kyrozen.core.stagegate import record_report_deliverable

                record_report_deliverable(workspace, "changelog", "changelog_confirmed")
            except Exception:
                pass
        return ToolResult(success=True, data=result)


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
