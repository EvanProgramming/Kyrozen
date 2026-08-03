"""Tools for manipulating Kyrozen projects from the agent runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kyrozen.core.stagegate import StageGateStore, advance as advance_stage, compute_gate, refresh_gate, sync_artifact_deliverables
from kyrozen.project.manager import ProjectManager
from kyrozen.project.workflow import stages_for

from .base import Tool, ToolParameter, ToolResult, ToolSchema


class UpdateProjectTool(Tool):
    """Allow the agent to update project metadata."""

    name = "update_project"
    description = "Update project metadata such as next steps or risks. Stage changes must use advance_project_stage so the unified gate cannot be bypassed."
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
                    description="Deprecated compatibility field; a different stage is rejected. Use advance_project_stage.",
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
            return ToolResult(success=False, data=None, error="Project manager not configured")

        project_id = parameters.get("project_id")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")

        project = self.project_manager.get(project_id)
        if project is None:
            return ToolResult(success=False, data=None, error=f"Project '{project_id}' not found")

        requested_stage = parameters.get("current_stage")
        if requested_stage is not None and requested_stage != project.current_stage:
            return ToolResult(
                success=False,
                data=None,
                error="不能通过 update_project 直接跳转阶段；请使用 advance_project_stage 让统一阶段门禁判断。",
            )

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
            return ToolResult(success=False, data=None, error="No fields provided to update")

        try:
            updated = self.project_manager.update(project_id, **updates)
            if updated is None:
                return ToolResult(success=False, data=None, error="Failed to update project")
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
            return ToolResult(success=False, data=None, error=str(e))


class AdvanceProjectStageTool(Tool):
    """Advance a project only through its persisted unified StageGate."""

    name = "advance_project_stage"
    description = "Evaluate and advance the current project workflow stage through the unified gate. Never changes stage by index or direct metadata update."
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "advance": [
                ToolParameter(name="project_id", param_type="string", description="Project ID", required=True),
            ]
        },
    )

    def __init__(self, project_manager: ProjectManager | None = None) -> None:
        super().__init__()
        self.project_manager = project_manager

    def _project_root(self, project_id: str) -> Path:
        if self.project_manager is None:
            raise RuntimeError("Project manager not configured")
        workspace_root = getattr(self.project_manager, "workspace_root", "")
        if not workspace_root:
            workspace_root = str(Path(getattr(self.project_manager.db, "db_path", "")).parent)
        return Path(workspace_root) / "projects" / project_id

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not configured")
        project_id = str(parameters.get("project_id") or "")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        project = self.project_manager.get(project_id)
        if project is None:
            return ToolResult(success=False, data=None, error=f"Project '{project_id}' not found")
        if project.current_stage == "problem_discovery" and not project.type_confirmed:
            return ToolResult(success=False, data=None, error="请先在问题探索阶段确认项目类型和对应流程")

        root = self._project_root(project_id)
        store = StageGateStore(
            root / ".kyrozen" / "stagegate.json",
            project_id=project_id,
            project_type=project.project_type,
        )
        store.set_workflow(project.project_type)

        # Keep the hard solution gate aligned with the versioned decision chain.
        decision = self.project_manager.get_latest_artifact(project_id, "solution_decision", title="Solution Decision")
        confirmed = False
        if decision is not None:
            try:
                confirmed = json.loads(decision.content).get("action") in {"select", "compose"}
            except (TypeError, json.JSONDecodeError):
                confirmed = False
        store.record_confirmation(
            "solution_confirmed",
            confirmed,
            detail="用户已确认方案" if confirmed else "尚未确认有效方案",
        )
        if store.current_stage != project.current_stage and project.current_stage in stages_for(project.project_type):
            # Cloud/project metadata may have been advanced by the API already;
            # do not invent a transition, only synchronize the persisted gate.
            store.current_stage = project.current_stage
            store.save()
        gate = refresh_gate(store, root)
        sync_artifact_deliverables(store, [artifact.type for artifact in self.project_manager.list_artifacts(project_id)])
        store.save()
        gate = compute_gate(store)
        stages = stages_for(project.project_type)
        if store.current_stage == stages[-1]:
            from kyrozen.phase2.workbench import build_workbench_snapshot

            readiness = build_workbench_snapshot(project, self.project_manager).get("phase2_completion", {})
            if not readiness.get("ready"):
                return ToolResult(
                    success=False,
                    error="第二阶段验收条件尚未全部满足",
                    data={"phase2_completion": readiness, "gate": gate.to_dict()},
                )
            return ToolResult(success=False, error="已是最后阶段，无法继续推进", data={"gate": gate.to_dict()})

        result = advance_stage(store, "normal")
        if not result.get("ok"):
            return ToolResult(success=False, error=str(result.get("error") or "阶段门禁未满足"), data={"gate": result.get("gate", {})})
        new_stage = str(result.get("stage", store.current_stage))
        updated = self.project_manager.update(
            project_id,
            current_stage=new_stage,
            progress=int(store.progress),
            next_steps=f"进入 {new_stage} 阶段",
            blocked_reason="",
        )
        if updated is None:
            return ToolResult(success=False, data=None, error="Failed to persist project stage")
        return ToolResult(
            success=True,
            data={"project_id": project_id, "current_stage": new_stage, "gate": result.get("gate", {})},
        )


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
