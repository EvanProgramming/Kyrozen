"""Build project context for Kyrozen Core conversations."""

from __future__ import annotations

import json
import os
from typing import Any

from kyrozen.discovery.brief import ProblemBrief
from kyrozen.memory.interface import MemoryInterface
from kyrozen.planning.models import PRD, ProductBrief
from kyrozen.research.models import MarketResearchReport

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

    def build_research_context(
        self,
        project: Project,
        memory: MemoryInterface | None = None,
        max_memories: int = 10,
    ) -> str:
        """Build context for Market Research mode."""
        memory_backend = memory or self.memory
        lines = ["[Market Research Context]"]
        lines.append(f"Project ID: {project.id}")
        lines.append(f"Project: {project.name}")
        if project.description:
            lines.append(f"Initial Idea: {project.description}")
        lines.append(f"Current Stage: {project.current_stage}")
        lines.append(
            "Your role: Evaluate whether the problem is worth solving. "
            "Do not design products, recommend technology, or do market research beyond the given scope.\n"
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

        lines.append("[Problem Brief]")
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

        latest_report = self.project_manager.get_latest_artifact(
            project.id, "market_research_report", title="Market Research Report"
        )
        if latest_report is not None:
            try:
                report = MarketResearchReport.from_dict(json.loads(latest_report.content))
                lines.append("\n[Current Market Research Report]")
                lines.append(f"  recommendation: {report.recommendation}")
                lines.append(f"  market_status: {report.market_status}")
                lines.append(f"  competitors: {len(report.competitors)}")
                lines.append(f"  sources: {len(report.sources)}")
            except (json.JSONDecodeError, ValueError):
                pass

        memories = memory_backend.query(
            category="research",
            limit=max_memories,
            project_id=project.id,
        )
        if memories:
            lines.append("\n[Recent Research Notes]")
            for mem in memories:
                lines.append(f"- {mem.content}")

        lines.append("\n[User Message]")
        return "\n".join(lines)

    def build_planning_context(
        self,
        project: Project,
        memory: MemoryInterface | None = None,
        max_memories: int = 10,
    ) -> str:
        """Build context for Product Planning mode."""
        memory_backend = memory or self.memory
        lines = ["[Product Planning Context]"]
        lines.append(f"Project ID: {project.id}")
        lines.append(f"Project: {project.name}")
        if project.description:
            lines.append(f"Initial Idea: {project.description}")
        lines.append(f"Current Stage: {project.current_stage}")
        lines.append(
            "Your role: Define what product to build, for whom, and why. "
            "Do not design technical architecture, choose technology, or write code.\n"
        )

        # Load Problem Brief
        latest_brief = self.project_manager.get_latest_artifact(
            project.id, "problem_brief", title="Problem Brief"
        )
        brief = ProblemBrief()
        if latest_brief is not None:
            try:
                brief = ProblemBrief.from_dict(json.loads(latest_brief.content))
            except (json.JSONDecodeError, ValueError):
                pass

        lines.append("[Problem Brief]")
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

        # Load Market Research Report
        latest_report = self.project_manager.get_latest_artifact(
            project.id, "market_research_report", title="Market Research Report"
        )
        if latest_report is not None:
            try:
                report = MarketResearchReport.from_dict(json.loads(latest_report.content))
                lines.append("\n[Market Research Report]")
                lines.append(f"  recommendation: {report.recommendation}")
                lines.append(f"  market_status: {report.market_status}")
                lines.append(f"  competitors: {len(report.competitors)}")
                lines.append(f"  technology_routes: {', '.join(report.technology_routes) or 'none'}")
                lines.append(f"  market_gap: {report.market_gap.possible_difference or 'none'}")
                lines.append(f"  risks: {', '.join(report.risks) or 'none'}")
            except (json.JSONDecodeError, ValueError):
                pass
        else:
            lines.append("\n[Market Research Report]")
            lines.append("  (no market research report available)")

        # Load existing Product Brief if any
        latest_product_brief = self.project_manager.get_latest_artifact(
            project.id, "product_brief", title="Product Brief"
        )
        if latest_product_brief is not None:
            try:
                product_brief = ProductBrief.from_dict(json.loads(latest_product_brief.content))
                lines.append("\n[Current Product Brief]")
                goal = product_brief.product_goal
                lines.append(f"  product_goal: {goal.product_goal or '(not set)'}")
                lines.append(f"  target_user: {product_brief.target_user.primary_user or '(not set)'}")
                lines.append(f"  value_proposition: {goal.value_proposition or '(not set)'}")
                lines.append(f"  mvp_features: {', '.join(product_brief.mvp_scope.mvp_features) or 'none'}")
            except (json.JSONDecodeError, ValueError):
                pass

        # Load recent planning memories
        memories = memory_backend.query(
            category="planning",
            limit=max_memories,
            project_id=project.id,
        )
        if memories:
            lines.append("\n[Recent Planning Notes]")
            for mem in memories:
                lines.append(f"- {mem.content}")

        lines.append("\n[User Message]")
        return "\n".join(lines)

    def _summarize_software_dir(self, project: Project, max_files: int = 20) -> str:
        """Return a short summary of the existing software project directory."""
        if self.project_manager is None:
            return ""
        software_dir = os.path.join(
            os.path.dirname(self.project_manager.db.db_path),
            "projects",
            project.id,
            "software",
        )
        if not os.path.isdir(software_dir):
            return ""
        try:
            entries = []
            for root, _dirs, files in os.walk(software_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), software_dir)
                    if ".git/" not in rel and not rel.startswith(".git/"):
                        entries.append(rel)
                        if len(entries) >= max_files:
                            break
                if len(entries) >= max_files:
                    break
            if not entries:
                return ""
            return "\n".join([f"  - {e}" for e in entries])
        except OSError:
            return ""

    def build_development_context(
        self,
        project: Project,
        memory: MemoryInterface | None = None,
        max_memories: int = 10,
    ) -> str:
        """Build context for Software Development mode."""
        memory_backend = memory or self.memory
        lines = ["[Software Development Context]"]
        lines.append(f"Project ID: {project.id}")
        lines.append(f"Project: {project.name}")
        if project.description:
            lines.append(f"Initial Idea: {project.description}")
        lines.append(f"Current Stage: {project.current_stage}")
        lines.append(
            "Your role: Turn the approved PRD into a runnable software prototype. "
            "Do not change product requirements, do not add out-of-scope features, "
            "and do not design hardware.\n"
        )

        # Load Product Brief
        latest_brief = self.project_manager.get_latest_artifact(
            project.id, "product_brief", title="Product Brief"
        )
        brief = ProductBrief()
        if latest_brief is not None:
            try:
                brief = ProductBrief.from_dict(json.loads(latest_brief.content))
            except (json.JSONDecodeError, ValueError):
                pass

        lines.append("[Product Brief]")
        lines.append(f"  product_goal: {brief.product_goal.product_goal or '(not set)'}")
        lines.append(f"  target_user: {brief.target_user.primary_user or '(not set)'}")
        lines.append(f"  value_proposition: {brief.product_goal.value_proposition or '(not set)'}")
        lines.append(f"  mvp_features: {', '.join(brief.mvp_scope.mvp_features) or 'none'}")

        # Load PRD
        latest_prd = self.project_manager.get_latest_artifact(
            project.id, "prd", title="Product Requirements Document"
        )
        prd = PRD()
        if latest_prd is not None:
            try:
                prd = PRD.from_dict(json.loads(latest_prd.content))
            except (json.JSONDecodeError, ValueError):
                pass

        lines.append("\n[PRD]")
        lines.append(f"  overview: {prd.overview or '(not set)'}")
        lines.append("  functional_requirements:")
        for req in prd.functional_requirements:
            lines.append(f"    - {req}")
        if not prd.functional_requirements:
            lines.append("    none")
        lines.append("  mvp_features:")
        for feat in prd.mvp_scope.mvp_features:
            lines.append(f"    - {feat}")
        if not prd.mvp_scope.mvp_features:
            lines.append("    none")
        lines.append("  out_of_scope:")
        for item in prd.out_of_scope:
            lines.append(f"    - {item}")
        if not prd.out_of_scope:
            lines.append("    none")

        # Load product decisions
        decisions = [
            d for d in self.project_manager.list_decisions(project.id)
            if d.decision.startswith("Product decision: ")
        ]
        if decisions:
            lines.append("\n[Approved Product Decisions]")
            for d in decisions[-5:]:
                lines.append(f"  - {d.decision}: {d.reason}")

        # Existing code summary
        code_summary = self._summarize_software_dir(project)
        if code_summary:
            lines.append("\n[Existing Software Project Files]")
            lines.append(code_summary)

        # Load recent development memories
        memories = memory_backend.query(
            category="development",
            limit=max_memories,
            project_id=project.id,
        )
        if memories:
            lines.append("\n[Recent Development Notes]")
            for mem in memories:
                lines.append(f"- {mem.content}")

        lines.append("\n[User Message]")
        return "\n".join(lines)
