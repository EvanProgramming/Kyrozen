"""Tools for problem discovery in Kyrozen Phase 3.

These tools allow the agent to save a Problem Brief artifact, record evidence,
and assess problem confidence without directly touching the database.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from kyrozen.discovery.brief import PROBLEM_DECISIONS, ProblemBrief
from kyrozen.discovery.evidence import Evidence, assess_confidence

from .base import Tool, ToolParameter, ToolResult, ToolSchema

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class SaveProblemBriefTool(Tool):
    """Save or update the Problem Brief artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_problem_brief"
        self.description = "Save or update the Problem Brief artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="brief", param_type="object", description="Problem Brief fields as a JSON object"),
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
            new_brief = ProblemBrief.from_dict(brief_data)
            existing = self.project_manager.get_latest_artifact(
                project_id, "problem_brief", title="Problem Brief"
            )
            if existing is not None:
                try:
                    current_brief = ProblemBrief.from_dict(json.loads(existing.content))
                    brief = current_brief.merge(new_brief)
                except (json.JSONDecodeError, ValueError):
                    brief = new_brief
            else:
                brief = new_brief
            content = json.dumps(brief.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="problem_brief",
                title="Problem Brief",
                content=content,
                change_reason="Discovery incremental update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class RecordEvidenceTool(Tool):
    """Record an evidence item for the current discovery session."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_evidence"
        self.description = "Record a claim, its source, and verification status as project evidence."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="claim", param_type="string", description="The claim or assumption to record"),
                    ToolParameter(name="source", param_type="string", description="Source: user_statement, ai_inference, external_evidence"),
                    ToolParameter(name="verified", param_type="boolean", description="Whether the claim is verified", required=False),
                    ToolParameter(name="notes", param_type="string", description="Optional notes", required=False),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        claim = parameters.get("claim")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        if not claim:
            return ToolResult(success=False, data=None, error="Missing claim")
        try:
            evidence = Evidence(
                claim=claim,
                source=parameters.get("source", "user_statement"),
                verified=parameters.get("verified", False),
                notes=parameters.get("notes", ""),
            )
            # Store evidence as a lightweight artifact for persistence
            content = json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="discovery_evidence",
                title=f"Evidence: {claim[:40]}",
                content=content,
                change_reason="New evidence recorded",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "evidence": evidence.to_dict()})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class AssessConfidenceTool(Tool):
    """Assess the confidence level of the current Problem Brief."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "assess_confidence"
        self.description = "Assess the confidence level of the current Problem Brief based on available information."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "assess": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        artifacts = self.project_manager.list_artifacts(project_id)
        brief_artifacts = [a for a in artifacts if a.type == "problem_brief"]
        if not brief_artifacts:
            return ToolResult(success=True, data={"confidence": "low", "reason": "No Problem Brief found."})
        latest = sorted(brief_artifacts, key=lambda a: a.version, reverse=True)[0]
        try:
            brief_data = json.loads(latest.content)
        except json.JSONDecodeError:
            return ToolResult(success=False, data=None, error="Problem Brief content is not valid JSON")
        confidence, reason = assess_confidence(brief_data)
        return ToolResult(success=True, data={"confidence": confidence, "reason": reason})


class RecordProblemDecisionTool(Tool):
    """Record a problem-level decision (e.g. continue research, not suitable)."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_problem_decision"
        self.description = "Record a problem-level decision for the project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="decision", param_type="string", description=f"One of: {', '.join(sorted(PROBLEM_DECISIONS))}"),
                    ToolParameter(name="reason", param_type="string", description="Reason for the decision"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        decision = parameters.get("decision")
        reason = parameters.get("reason", "")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        if decision not in PROBLEM_DECISIONS:
            return ToolResult(success=False, data=None, error=f"Invalid decision '{decision}'")
        try:
            recorded = self.project_manager.add_decision(
                project_id=project_id,
                decision=f"Problem decision: {decision}",
                reason=reason,
                source="agent",
            )
            return ToolResult(success=True, data={"decision_id": recorded.id, "decision": decision})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
