"""Problem Discovery Agent for Kyrozen Phase 3.

This agent inherits from BaseAgent and specializes in helping users move from a
vague idea to a structured Problem Brief. It never designs products, suggests
technology, or performs market research.
"""

from __future__ import annotations

import json
from typing import Any

from kyrozen.core.agent import BaseAgent
from kyrozen.project import ProjectManager

from .brief import ProblemBrief
from .evidence import Evidence, assess_confidence
from .question_engine import QuestionEngine
from .state import DiscoverySession


class ProblemDiscoveryAgent(BaseAgent):
    """Agent specialized in problem discovery and problem brief generation."""

    def __init__(self, *args: Any, project_manager: ProjectManager | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager
        self.question_engine = QuestionEngine()

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Problem Discovery Agent. Your job is to help the user "
            "understand the real problem behind their vague idea, before any product "
            "design or market research begins.\n\n"
            "When you need to use a tool, output a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "If no tool is needed, reply with a plain text answer.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "Rules:\n"
            "- DO NOT design a product, recommend technology, suggest hardware, or write code.\n"
            "- DO NOT perform market research, competitor analysis, or search for external data.\n"
            "- DO NOT assume the user's initial idea is correct. Ask why they have this idea.\n"
            "- Ask only 1 or 2 focused follow-up questions at a time. Never dump a long questionnaire.\n"
            "- Explore these dimensions step by step: Who, Where/When, Surface Problem, Current Solution, Pain Point, Deep Need, Frequency, Impact.\n"
            "- When the user makes a broad claim (e.g. 'many people have this problem'), treat it as an unverified assumption.\n"
            "- When enough information is gathered, call save_problem_brief to update the Problem Brief artifact.\n"
            "- Use record_evidence to mark important claims and their source.\n"
            "- After updating the brief, use assess_confidence to evaluate confidence.\n"
            "- If the problem already has a simple existing solution (e.g. phone alarm for drinking water), say so and suggest existing_solution_enough.\n"
            "- Only update project state or record decisions when the user explicitly asks.\n"
        )

    def build_discovery_context(
        self,
        project_id: str,
        session: DiscoverySession | None = None,
    ) -> str:
        """Build a context string that includes the current brief and recent Q&A."""
        if self.project_manager is None:
            return ""

        project = self.project_manager.get(project_id)
        if project is None:
            return ""

        lines = ["[Problem Discovery Context]"]
        lines.append(f"Project ID: {project.id}")
        lines.append(f"Project: {project.name}")
        if project.description:
            lines.append(f"Initial Idea: {project.description}")
        lines.append(f"Current Stage: {project.current_stage}")
        lines.append(
            "Your role: Help the user understand the real problem. Do not design products or do market research.\n"
        )

        brief = session.brief if session else ProblemBrief()
        lines.append("[Current Problem Brief]")
        brief_dict = brief.to_dict()
        for key, value in brief_dict.items():
            if key == "unknown_assumptions":
                if value:
                    lines.append(f"  {key}:")
                    for item in value:
                        lines.append(f"    - {item['claim']} (source: {item['source']}, verified: {item['verified']})")
                else:
                    lines.append(f"  {key}: none")
            else:
                display_value = value if value else "(not set)"
                lines.append(f"  {key}: {display_value}")

        if session and session.history:
            lines.append("\n[Recent Discovery Q&A]")
            for item in session.history[-5:]:
                lines.append(f"Q: {item['question']}")
                lines.append(f"A: {item['answer']}")

        next_q = self.question_engine.next_question(brief)
        if next_q:
            lines.append(f"\n[Recommended Next Question] {next_q.question}")

        lines.append("\n[User Message]")
        return "\n".join(lines)

    def summarize_brief_from_evidence(self, session: DiscoverySession) -> ProblemBrief:
        """Re-evaluate confidence and decision for the current brief."""
        brief = session.brief
        confidence, reason = assess_confidence(brief.to_dict())
        brief.confidence = confidence
        brief.confidence_reason = reason
        return brief
