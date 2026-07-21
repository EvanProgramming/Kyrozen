"""Build project context for Kyrozen Core conversations."""

from __future__ import annotations

import json
from typing import Any

from kyrozen.discovery.brief import ProblemBrief
from kyrozen.memory.interface import MemoryInterface

from .manager import ProjectManager
from .project import PROJECT_STAGES, Project


class ProjectContextBuilder:
    """Assemble project context to inject into agent conversations."""

    def __init__(self, project_manager: ProjectManager, memory: MemoryInterface) -> None:
        self.project_manager = project_manager
        self.memory = memory

    def build(
        self,
        project: Project,
        memory: MemoryInterface | None = None,
        max_tasks: int = 5,
        max_decisions: int = 5,
        max_memories: int = 5,
    ) -> str:
        """Build a context string for the given project."""
        memory_backend = memory or self.memory
        lines: list[str] = ["[Project Context]"]
        lines.append(f"Project ID: {project.id}")
        lines.append(f"Project: {project.name}")
        if project.goal:
            lines.append(f"Goal: {project.goal}")
        if project.description:
            lines.append(f"Description: {project.description}")
        lines.append(f"Current Stage: {project.current_stage}")
        lines.append(f"Status: {project.status}")
        if project.next_steps:
            lines.append(f"Next Steps: {project.next_steps}")
        if project.risks:
            lines.append(f"Risks: {'; '.join(project.risks)}")

        tasks = self.project_manager.list_tasks(project.id)[:max_tasks]
        if tasks:
            lines.append("\nRecent Tasks:")
            for task in tasks:
                result_summary = ""
                if task.result and isinstance(task.result, dict) and "answer" in task.result:
                    result_summary = f" -> {task.result['answer'][:80]}"
                lines.append(f"- {task.title} ({task.status}){result_summary}")
        else:
            lines.append("\nRecent Tasks: none")

        decisions = self.project_manager.list_decisions(project.id)[:max_decisions]
        if decisions:
            lines.append("\nRecent Decisions:")
            for d in decisions:
                lines.append(f"- {d.decision} (reason: {d.reason})")
        else:
            lines.append("\nRecent Decisions: none")

        memories = memory_backend.query(
            category="project",
            query=project.name,
            limit=max_memories,
            project_id=project.id,
        )
        if memories:
            lines.append("\nRelevant Project Memories:")
            for mem in memories:
                lines.append(f"- {mem.content}")
        else:
            lines.append("\nRelevant Project Memories: none")

        lines.append(f"\nValid project stages: {', '.join(sorted(PROJECT_STAGES))}")
        lines.append("You may use the update_project tool to update current_stage, next_steps, or risks ONLY when the user explicitly asks you to.")
        lines.append("DO NOT write files, execute commands, or update project state unless the user explicitly asks you to.")
        lines.append("\n[User Message]")
        return "\n".join(lines)

    def build_for_project_id(self, project_id: str, **kwargs: Any) -> str | None:
        """Load project and build context; return None if not found."""
        project = self.project_manager.get(project_id)
        if project is None:
            return None
        return self.build(project, **kwargs)

    def build_discovery_context(
        self,
        project: Project,
        memory: MemoryInterface | None = None,
        max_memories: int = 10,
    ) -> str:
        """Build context for Problem Discovery mode."""
        memory_backend = memory or self.memory
        lines = ["[Problem Discovery Context]"]
        lines.append(f"Project ID: {project.id}")
        lines.append(f"Project: {project.name}")
        if project.description:
            lines.append(f"Initial Idea: {project.description}")
        lines.append(f"Current Stage: {project.current_stage}")
        lines.append(
            "Your role: Help the user understand the real problem. "
            "Do not design products, recommend technology, or do market research.\n"
        )

        latest_brief = self.project_manager.get_latest_artifact(
            project.id, "problem_brief", title="Problem Brief"
        )
        brief = ProblemBrief()
        if latest_brief is not None:
            try:
                brief = ProblemBrief.from_dict(json.loads(latest_brief.content))
            except (json.JSONDecodeError, ValueError):
                pass

        lines.append("[Current Problem Brief]")
        brief_dict = brief.to_dict()
        for key, value in brief_dict.items():
            if key == "unknown_assumptions":
                if value:
                    lines.append(f"  {key}:")
                    for item in value:
                        lines.append(
                            f"    - {item['claim']} (source: {item['source']}, verified: {item['verified']})"
                        )
                else:
                    lines.append(f"  {key}: none")
            else:
                display_value = value if value else "(not set)"
                lines.append(f"  {key}: {display_value}")

        memories = memory_backend.query(
            category="discovery_qa",
            limit=max_memories,
            project_id=project.id,
        )
        if memories:
            lines.append("\n[Recent Discovery Q&A]")
            for mem in memories:
                question = mem.metadata.get("question", "")
                answer = mem.content
                if question:
                    lines.append(f"Q: {question}")
                    lines.append(f"A: {answer}")
                else:
                    lines.append(f"- {answer}")

        lines.append("\n[User Message]")
        return "\n".join(lines)
