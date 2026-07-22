"""Tools for product planning in Kyrozen Phase 5.

These tools allow the agent to save Product Brief, PRD, Solution Comparison,
and record product decisions without directly touching the database.
"""

from __future__ import annotations

import json
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
    """Save or update the PRD artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_prd"
        self.description = "Save or update the Product Requirements Document (PRD) artifact."
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

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        prd_data = parameters.get("prd", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            prd = PRD.from_dict(prd_data)
            content = json.dumps(prd.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="prd",
                title="Product Requirements Document",
                content=content,
                change_reason="PRD update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


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
