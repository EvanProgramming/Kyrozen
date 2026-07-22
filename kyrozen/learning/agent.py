"""Learning and Proactive Improvement Agent for Kyrozen Phase 9."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from kyrozen.core.agent import BaseAgent

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class LearningAgent(BaseAgent):
    """Agent specialized in extracting reusable knowledge and generating improvement suggestions."""

    def __init__(
        self,
        *args: Any,
        project_manager: "ProjectManager | None" = None,
        memory: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager
        self.memory = memory

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Learning & Proactive Improvement Agent. Your job is to help Kyrozen "
            "accumulate experience from projects, distinguish facts from assumptions, and proactively "
            "suggest improvements without automatically changing anything.\n\n"
            "When you need to use a tool, output a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "If no tool is needed, reply with a plain text answer.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "Rules:\n"
            "- ALWAYS classify every piece of learning into one of: user_preference, user_capability, "
            "project_fact, product_decision, validated_success, validated_failure, external_knowledge.\n"
            "- Every learning record MUST include confidence (low/medium/high) and verification_status "
            "(unverified/user_provided/externally_verified/experiment_verified/repeatedly_verified).\n"
            "- Learning records default to scope=private. Only promote to scope=user or scope=public "
            "when the user explicitly allows cross-project reuse.\n"
            "- Use extract_learning_from_event to analyze project events (test_result, user_feedback, "
            "validation_report, iteration_plan, hardware_debug, decision) and review proposed records "
            "before saving them.\n"
            "- Use save_learning_record, save_failure_knowledge, and save_success_knowledge to persist "
            "validated learnings.\n"
            "- Use delete_learning_record to remove incorrect memories when the user asks.\n"
            "- Use run_project_analysis to generate proactive suggestions for the current project.\n"
            "- Use save_suggestion to persist new suggestions, and update_suggestion_status when the user "
            "accepts, rejects, postpones, or ignores a suggestion.\n"
            "- Do NOT modify project code, BOM, PRD, or hardware without explicit user confirmation. "
            "Only generate suggestions.\n"
            "- Do NOT treat every chat message as knowledge. Extract, classify, and verify first.\n"
            "- Do NOT leak private project details across projects. Respect the scope field.\n"
            "- Focus on failures as high-value learning sources, especially hardware_debug records.\n"
        )
