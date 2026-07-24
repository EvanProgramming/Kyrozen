"""Project manager for CRUD and related operations."""

from __future__ import annotations

from typing import Any

from .db import KyrozenDatabase
from .project import Artifact, Decision, Project


class ProjectManager:
    """High-level manager for project workspaces."""

    def __init__(self, db: KyrozenDatabase, workspace_root: str = "") -> None:
        self.db = db
        self.workspace_root = workspace_root

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def create(
        self,
        name: str,
        description: str = "",
        goal: str = "",
        initial_idea: str = "",
        user_id: str = "",
    ) -> Project:
        """Create a new project."""
        description = description or initial_idea
        project = Project(
            name=name,
            description=description,
            goal=goal,
            next_steps="Clarify project goals and scope",
            user_id=user_id,
        )
        self.db.save_project(project)
        return project

    def get(self, project_id: str) -> Project | None:
        return self.db.get_project(project_id)

    def list(self, user_id: str | None = None) -> list[Project]:
        return self.db.list_projects(user_id=user_id)

    def update(self, project_id: str, **kwargs: Any) -> Project | None:
        project = self.db.get_project(project_id)
        if project is None:
            return None
        project.update(**kwargs)
        self.db.save_project(project)
        return project

    def archive(self, project_id: str) -> Project | None:
        return self.update(project_id, status="archived")

    def restore(self, project_id: str) -> Project | None:
        """Restore an archived project back to active status."""
        project = self.db.get_project(project_id)
        if project is None or project.status != "archived":
            return None
        return self.update(project_id, status="active")

    def delete(self, project_id: str) -> bool:
        return self.db.delete_project(project_id)

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def add_decision(
        self,
        project_id: str,
        decision: str,
        reason: str = "",
        alternatives: list[str] | None = None,
        rejected_reasons: dict[str, str] | None = None,
        source: str = "agent",
    ) -> Decision:
        """Record a decision in the project."""
        if self.db.get_project(project_id) is None:
            raise ValueError(f"Project '{project_id}' not found")
        dec = Decision(
            project_id=project_id,
            decision=decision,
            reason=reason,
            alternatives=alternatives or [],
            rejected_reasons=rejected_reasons or {},
            source=source,
        )
        self.db.save_decision(dec)
        return dec

    def list_decisions(self, project_id: str) -> list[Decision]:
        return self.db.list_decisions(project_id)

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    def save_artifact(
        self,
        project_id: str,
        type: str,
        title: str,
        content: str,
        change_reason: str = "",
    ) -> Artifact:
        """Save a project artifact. If an artifact of the same type/title exists, bump version."""
        if self.db.get_project(project_id) is None:
            raise ValueError(f"Project '{project_id}' not found")
        existing = self._find_existing_artifact(project_id, type, title)
        if existing:
            artifact = existing.bump_version(content, change_reason=change_reason)
        else:
            artifact = Artifact(
                project_id=project_id,
                type=type,
                title=title,
                content=content,
                change_reason=change_reason,
            )
        self.db.save_artifact(artifact)
        return artifact

    def _find_existing_artifact(
        self, project_id: str, type: str, title: str
    ) -> Artifact | None:
        for artifact in self.db.list_artifacts(project_id):
            if artifact.type == type and artifact.title == title:
                return artifact
        return None

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        return self.db.list_artifacts(project_id)

    def get_artifact(self, project_id: str, artifact_id: str) -> Artifact | None:
        artifact = self.db.get_artifact(artifact_id)
        if artifact and artifact.project_id == project_id:
            return artifact
        return None

    def get_latest_artifact(self, project_id: str, artifact_type: str, title: str | None = None) -> Artifact | None:
        """Return the latest version of an artifact of the given type."""
        artifacts = self.db.list_artifacts(project_id)
        matches = [a for a in artifacts if a.type == artifact_type]
        if title:
            matches = [a for a in matches if a.title == title]
        if not matches:
            return None
        return sorted(matches, key=lambda a: a.version, reverse=True)[0]

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def list_tasks(self, project_id: str) -> list[Any]:
        return self.db.list_tasks(project_id=project_id)

    # ------------------------------------------------------------------
    # Chat messages
    # ------------------------------------------------------------------
    def save_chat_message(self, message: dict[str, Any]) -> None:
        self.db.save_chat_message(message)

    def list_chat_messages(
        self,
        project_id: str,
        user_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self.db.list_chat_messages(project_id=project_id, user_id=user_id, limit=limit)

    def delete_chat_messages(self, project_id: str, user_id: str) -> bool:
        return self.db.delete_chat_messages(project_id=project_id, user_id=user_id)
