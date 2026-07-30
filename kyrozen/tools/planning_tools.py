"""Tools for product planning in Kyrozen Phase 5.

These tools allow the agent to save Product Brief, PRD, Solution Comparison,
and record product decisions without directly touching the database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.planning.models import PRODUCT_DECISIONS, PRD, ProductBrief, SolutionComparison

from .base import Tool, ToolParameter, ToolResult, ToolSchema

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class SaveProductBriefTool(Tool):
    """Save or update the Product Brief artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_product_brief"
        self.description = "Save or update the Product Brief artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="brief", param_type="object", description="Product Brief fields as a JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        brief_data = parameters.get("brief", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            brief = ProductBrief.from_dict(brief_data)
            content = json.dumps(brief.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="product_brief",
                title="Product Brief",
                content=content,
                change_reason="Product planning update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SavePRDTool(Tool):
    """Save or update the PRD artifact for a project.

    In addition to persisting the PRD to the project artifact store (when a
    project manager is available), this tool ALWAYS writes a real ``PRD.md`` /
    ``docs/PRD.md`` file into the workspace. The product_definition stage gate
    detects the PRD by scanning for that file; without it the hard gate into
    development can never be satisfied, so the file write is mandatory regardless
    of whether the cloud artifact store is reachable.
    """

    def __init__(self, project_manager: "ProjectManager | None" = None, config: Any = None) -> None:
        self.project_manager = project_manager
        self.config = config
        self.name = "save_prd"
        self.description = "Save or update the Product Requirements Document (PRD) and write it to PRD.md."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="prd", param_type="object", description="PRD fields as a JSON object"),
                ]
            },
        )

    @staticmethod
    def _resolve_workspace(project_id, project_manager, config):
        # Server: a ProjectManager is present, so the workspace is the
        # project-scoped directory. On the desktop the ProjectManager is None and
        # config.workspace_root points directly at the user-selected workspace.
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
    def _render_markdown(prd) -> str:
        d = prd.to_dict() if hasattr(prd, "to_dict") else dict(prd)
        lines = ["# Product Requirements Document (PRD)", ""]

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

        block("概览 Overview", d.get("overview", ""))
        block("用户故事 User Stories", d.get("user_stories", []))
        block("功能需求 Functional Requirements", d.get("functional_requirements", []))
        block("非功能需求 Non-Functional Requirements", d.get("non_functional_requirements", []))
        block("MVP 范围 MVP Scope", d.get("mvp_scope", {}))
        block("范围外 Out of Scope", d.get("out_of_scope", []))
        return chr(10).join(lines)

    _PLACEHOLDERS = {"", "无", "(无)", "暂无", "n/a", "na", "none", "null", "tbd", "待定", "-"}

    @classmethod
    def _is_placeholder(cls, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().lower() in cls._PLACEHOLDERS
        if isinstance(value, (list, dict)):
            if not value:
                return True
            if isinstance(value, list):
                return all(cls._is_placeholder(v) for v in value)
            return all(cls._is_placeholder(v) for v in value.values())
        return False

    @classmethod
    def _validate_quality(cls, prd) -> list[str]:
        """Return human-readable reasons why the PRD is too hollow to save."""
        d = prd.to_dict() if hasattr(prd, "to_dict") else dict(prd)
        errors: list[str] = []
        required = {
            "overview": "概览 Overview 不能为空",
            "user_stories": "用户故事 User Stories 至少需要 1 条真实内容",
            "functional_requirements": "功能需求 Functional Requirements 至少需要 1 条真实内容",
        }
        for key, message in required.items():
            if cls._is_placeholder(d.get(key)):
                errors.append(message)
        # An overview of only a couple of characters is a stub in disguise.
        overview = d.get("overview")
        if (
            isinstance(overview, str)
            and not cls._is_placeholder(overview)
            and len(overview.strip()) <= 3
        ):
            errors.append("概览 Overview 过于简略（不足 3 字）")
        return errors

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        project_id = parameters.get("project_id")
        prd_data = parameters.get("prd", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            prd = PRD.from_dict(prd_data)
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
        # GATE HONESTY: a hollow PRD (empty/placeholder required sections) must
        # NOT be written to disk, because PRD.md existence is the hard gate into
        # development. Reject with actionable reasons so the model regenerates a
        # complete PRD instead of shipping "无".
        quality_errors = self._validate_quality(prd)
        if quality_errors:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    "PRD 内容不完整，已拒绝保存（PRD 是进入开发阶段的硬门禁，不允许空洞内容）："
                    + "；".join(quality_errors)
                    + "。请补全后重新调用 save_prd，内容必须覆盖用户明确提出的全部需求。"
                ),
            )
        result: dict[str, Any] = {}
        # Best-effort artifact persistence (not required on the desktop).
        if self.project_manager is not None:
            try:
                content = json.dumps(prd.to_dict(), ensure_ascii=False, indent=2)
                artifact = self.project_manager.save_artifact(
                    project_id=project_id,
                    type="prd",
                    title="Product Requirements Document",
                    content=content,
                    change_reason="PRD update",
                )
                result["artifact_id"] = artifact.id
                result["version"] = artifact.version
            except Exception:
                pass
        # MANDATORY: write the real PRD.md deliverable so the stage gate detects it.
        workspace = self._resolve_workspace(project_id, self.project_manager, self.config)
        if workspace:
            try:
                out = Path(workspace) / "PRD.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(self._render_markdown(prd), encoding="utf-8")
                result["file"] = str(out)
            except Exception:
                pass
        if not result:
            return ToolResult(
                success=False,
                data=None,
                error="无法保存 PRD：未找到可写的项目工作区，且项目管理器不可用。",
            )
        # Auto-confirm the paired confirmation item now that the file exists.
        if workspace and result.get("file"):
            try:
                from kyrozen.core.stagegate import record_report_deliverable

                record_report_deliverable(workspace, "prd", "prd_confirmed")
            except Exception:
                pass
        return ToolResult(success=True, data=result)


class SaveSolutionComparisonTool(Tool):
    """Save or update the Solution Comparison artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_solution_comparison"
        self.description = "Save or update the Solution Comparison artifact."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="comparison", param_type="object", description="Solution Comparison fields as a JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        comparison_data = parameters.get("comparison", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            comparison = SolutionComparison.from_dict(comparison_data)
            content = json.dumps(comparison.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="solution_comparison",
                title="Solution Comparison",
                content=content,
                change_reason="Solution comparison update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class RecordProductDecisionTool(Tool):
    """Record a major product decision in the project workspace."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_product_decision"
        self.description = "Record a product decision, the reason, and rejected alternatives."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="decision", param_type="string", description=f"Decision: one of {', '.join(sorted(PRODUCT_DECISIONS))}"),
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
        if decision not in PRODUCT_DECISIONS:
            return ToolResult(
                success=False,
                data=None,
                error=f"Invalid decision '{decision}'. Valid: {', '.join(sorted(PRODUCT_DECISIONS))}",
            )
        try:
            dec = self.project_manager.add_decision(
                project_id=project_id,
                decision=f"Product decision: {decision}",
                reason=reason,
                alternatives=list(parameters.get("alternatives") or []),
                rejected_reasons=dict(parameters.get("rejected_reasons") or {}),
                source="agent",
            )
            return ToolResult(success=True, data={"decision_id": dec.id, "decision": decision})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
