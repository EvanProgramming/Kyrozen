"""Tools for problem discovery in Kyrozen Phase 3.

These tools allow the agent to save a Problem Brief artifact, record evidence,
and assess problem confidence without directly touching the database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.discovery.brief import PROBLEM_DECISIONS, ProblemBrief
from kyrozen.discovery.evidence import Evidence, assess_confidence

from .base import Tool, ToolParameter, ToolResult, ToolSchema
from ._paths import _get_allowed_root

if TYPE_CHECKING:
    from kyrozen.config import Config
    from kyrozen.project import ProjectManager


class SaveProblemBriefTool(Tool):
    """Save or update the Problem Brief artifact for a project.

    In addition to persisting the brief to the project artifact store (when a
    project manager is available), this tool ALWAYS writes a real
    ``docs/PROBLEM.md`` file into the workspace. Phase 1's stage gate detects
    the problem statement by scanning for ``docs/PROBLEM.md``; without that
    file the gate can never advance, so the file write is mandatory regardless
    of whether the cloud artifact store is reachable.
    """

    def __init__(
        self,
        project_manager: "ProjectManager | None" = None,
        config: "Config | None" = None,
    ) -> None:
        self.project_manager = project_manager
        self.config = config
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

    def _resolve_workspace_root(self, parameters: dict[str, Any]) -> Path | None:
        """Resolve the workspace root so we can write docs/PROBLEM.md.

        Prefer the live agent config (set per-task to the project workspace),
        then fall back to the global config / project_id lookup.
        """
        candidates: list[Path] = []
        if self.config is not None:
            ws = getattr(self.config, "workspace_root", None)
            if ws and str(ws) not in (".", "", None):
                candidates.append(Path(str(ws)).resolve())
            else:
                # Fallback: the desktop agent sets projects_dir to the workspace
                # parent and passes project_id to the tool, so
                # <projects_dir>/<project_id> reconstructs the exact workspace.
                pd = getattr(self.config, "projects_dir", None)
                pid = parameters.get("project_id")
                if pd and pid:
                    cand = Path(str(pd)) / str(pid)
                    if cand.is_absolute():
                        candidates.append(cand)
        try:
            candidates.append(_get_allowed_root(parameters).resolve())
        except Exception:
            pass
        for candidate in candidates:
            if candidate and candidate.is_absolute():
                return candidate
        return None

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        project_id = parameters.get("project_id")
        brief_data = parameters.get("brief", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            new_brief = ProblemBrief.from_dict(brief_data)

            # Merge with any previously stored brief so incremental updates
            # accumulate rather than overwrite.
            brief = new_brief
            if self.project_manager is not None:
                try:
                    existing = self.project_manager.get_latest_artifact(
                        project_id, "problem_brief", title="Problem Brief"
                    )
                    if existing is not None:
                        try:
                            current_brief = ProblemBrief.from_dict(json.loads(existing.content))
                            brief = current_brief.merge(new_brief)
                        except (json.JSONDecodeError, ValueError):
                            brief = new_brief
                except Exception:
                    # Artifact store may be unavailable (offline / local-only);
                    # the workspace file below is the source of truth for the gate.
                    pass

            # Persist the artifact to the cloud/local project store when possible.
            artifact_id = None
            artifact_version = None
            if self.project_manager is not None:
                try:
                    content = json.dumps(brief.to_dict(), ensure_ascii=False, indent=2)
                    artifact = self.project_manager.save_artifact(
                        project_id=project_id,
                        type="problem_brief",
                        title="Problem Brief",
                        content=content,
                        change_reason="Discovery incremental update",
                    )
                    artifact_id = artifact.id
                    artifact_version = artifact.version
                except Exception:
                    pass

            # MANDATORY: write the real docs/PROBLEM.md deliverable so the stage
            # gate detects the problem statement and the user can open it.
            written_path = None
            root = self._resolve_workspace_root(parameters)
            if root is not None:
                try:
                    docs_dir = root / "docs"
                    docs_dir.mkdir(parents=True, exist_ok=True)
                    problem_md = docs_dir / "PROBLEM.md"
                    problem_md.write_text(brief.to_markdown(), encoding="utf-8")
                    written_path = str(problem_md)
                    self._refresh_problem_stage(root, project_id)
                except Exception as exc:  # pragma: no cover - defensive
                    return ToolResult(
                        success=False,
                        data={"artifact_id": artifact_id, "version": artifact_version, "path": written_path},
                        error=f"Failed to write docs/PROBLEM.md: {exc}",
                    )

            if written_path is None and artifact_id is None:
                # Nothing could be persisted — surface a clear failure.
                missing = "no workspace root resolved and no project manager available"
                return ToolResult(success=False, data=None, error=f"Could not persist Problem Brief ({missing})")

            return ToolResult(
                success=True,
                data={"artifact_id": artifact_id, "version": artifact_version, "path": written_path},
            )
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _refresh_problem_stage(self, root: Path, project_id: str) -> None:
        """Re-scan the stage gate so the freshly written PROBLEM.md is detected,
        then auto-confirm the paired confirmation item."""
        try:
            from kyrozen.core.stagegate import record_report_deliverable

            record_report_deliverable(str(root), "problem_statement", "problem_confirmed")
        except Exception:
            pass


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
