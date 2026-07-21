"""Tools for manipulating Kyrozen projects from the agent runtime."""

from __future__ import annotations

from typing import Any

from kyrozen.project.manager import ProjectManager
from kyrozen.project.project import PROJECT_STAGES

from .base import Tool, ToolParameter, ToolResult, ToolSchema


class UpdateProjectTool(Tool):
    """Allow the agent to update project metadata."""

    name = "update_project"
    description = "Update project metadata such as current stage, next steps, or risks. Use this when the project state should advance based on the conversation."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "update": [
                ToolParameter(
                    name="project_id",
                    param_type="string",
                    description="ID of the project to update",
                    required=True,
                ),
                ToolParameter(
                    name="current_stage",
                    param_type="string",
                    description=f"New project stage. Valid: {', '.join(sorted(PROJECT_STAGES))}",
                    required=False,
                ),
                ToolParameter(
                    name="next_steps",
                    param_type="string",
                    description="Updated next steps for the project",
                    required=False,
                ),
                ToolParameter(
                    name="risks",
                    param_type="array",
                    description="List of project risks to set (replaces existing)",
                    required=False,
                ),
                ToolParameter(
                    name="goal",
                    param_type="string",
                    description="Updated project goal",
                    required=False,
                ),
            ]
        },
    )

    def __init__(self, project_manager: ProjectManager | None = None) -> None:
        super().__init__()
        self.project_manager = project_manager

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, error="Project manager not configured")

        project_id = parameters.get("project_id")
        if not project_id:
            return ToolResult(success=False, error="Missing project_id")

        project = self.project_manager.get(project_id)
        if project is None:
            return ToolResult(success=False, error=f"Project '{project_id}' not found")

        updates: dict[str, Any] = {}
        for field in ["current_stage", "next_steps", "goal"]:
            if field in parameters:
                updates[field] = parameters[field]

        if "risks" in parameters:
            risks = parameters["risks"]
            if isinstance(risks, str):
                risks = [risks]
            updates["risks"] = list(risks)

        if not updates:
            return ToolResult(success=False, error="No fields provided to update")

        try:
            updated = self.project_manager.update(project_id, **updates)
            if updated is None:
                return ToolResult(success=False, error="Failed to update project")
            return ToolResult(
                success=True,
                data={
                    "project_id": updated.id,
                    "updated_fields": list(updates.keys()),
                    "current_stage": updated.current_stage,
                    "next_steps": updated.next_steps,
                },
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))


class RecordDecisionTool(Tool):
    """Allow the agent to record a project decision."""

    name = "record_decision"
    description = "Record a decision made during the project, including the reason and rejected alternatives."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "record": [
                ToolParameter(
                    name="project_id",
                    param_type="string",
                    description="ID of the project",
                    required=True,
                ),
                ToolParameter(
                    name="decision",
                    param_type="string",
                    description="The decision made",
                    required=True,
                ),
                ToolParameter(
                    name="reason",
                    param_type="string",
                    description="Why this decision was made",
                    required=True,
                ),
                ToolParameter(
                    name="alternatives",
                    param_type="array",
                    description="Alternatives that were considered",
                    required=False,
                ),
                ToolParameter(
                    name="rejected_reasons",
                    param_type="object",
                    description="Map of rejected alternative -> reason for rejection",
                    required=False,
                ),
            ]
        },
    )

    def __init__(self, project_manager: ProjectManager | None = None) -> None:
        super().__init__()
        self.project_manager = project_manager

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, error="Project manager not configured")

        project_id = parameters.get("project_id")
        decision = parameters.get("decision")
        reason = parameters.get("reason", "")
        if not project_id or not decision:
            return ToolResult(success=False, error="Missing project_id or decision")

        alternatives = parameters.get("alternatives", [])
        rejected_reasons = parameters.get("rejected_reasons", {})
        try:
            dec = self.project_manager.add_decision(
                project_id=project_id,
                decision=decision,
                reason=reason,
                alternatives=alternatives if isinstance(alternatives, list) else [alternatives],
                rejected_reasons=rejected_reasons if isinstance(rejected_reasons, dict) else {},
                source="agent",
            )
            return ToolResult(success=True, data={"decision_id": dec.id})
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
