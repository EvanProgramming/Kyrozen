"""Product Planning Agent for Kyrozen Phase 5.

The agent receives a Problem Brief and Market Research Report, then produces
a Product Brief, PRD, Solution Comparison, and product decisions.

It also serves the ``solution_design`` stage (routed via ``route_mode``), where
its PRIMARY REQUIRED OUTPUT is the technical design document saved with
``save_technical_plan`` -- the stage gate scans for ``docs/TECH_DESIGN.md`` and
can never advance without it. Real acceptance (2026-07-30 round 2) found the
agent announcing "下面开始保存" and stopping without calling the tool, so the
base loop now enforces the call via ``required_actions`` and fails the task
explicitly (with a retry entry in the UI) when the model refuses to act.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.core.agent import BaseAgent

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


_DESIGN_INTENT_RE = re.compile(
    r"技术方案|方案设计|技术设计|架构|TECH_DESIGN|设计文档|生成.*方案|保存.*方案|"
    r"文件结构|数据模型|技术选型|\bdesign\b|\barchitecture\b|\btech\s*plan\b",
    re.IGNORECASE,
)


class ProductPlanningAgent(BaseAgent):
    """Agent specialized in product planning and solution decision making."""

    def __init__(self, *args: Any, project_manager: "ProjectManager | None" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager

    # ------------------------------------------------------------------ hooks

    @property
    def required_actions(self) -> tuple[str, ...]:  # type: ignore[override]
        if getattr(self, "route_mode", "") == "solution_design":
            return ("save_technical_plan",)
        return ()

    def _action_required(self, user_input: str) -> bool:
        if getattr(self, "route_mode", "") != "solution_design":
            return False
        if not _DESIGN_INTENT_RE.search(user_input or ""):
            return False
        ws = getattr(self.config, "workspace_root", None)
        if ws:
            try:
                if (Path(ws) / "docs" / "TECH_DESIGN.md").exists():
                    return False
            except Exception:
                pass
        return True

    # ----------------------------------------------------------------- prompt

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        solution_design = getattr(self, "route_mode", "") == "solution_design"

        if solution_design:
            mission = (
                "You are Kyrozen Solution Design Agent. Your job is to turn the confirmed PRD "
                "into a concrete, buildable technical design, and you MUST persist it by calling "
                "save_technical_plan (it writes docs/TECH_DESIGN.md, which the stage gate requires).\n\n"
            )
            mandate = (
                "CRITICAL EXECUTION RULES:\n"
                "- When the user asks for the technical design/方案, produce it AND call "
                "save_technical_plan IN THE SAME TURN. NEVER end your reply with an announcement "
                "like '下面开始保存' or 'I will now save it' -- announcing without the tool-call JSON "
                "is a failure.\n"
                "- The plan object should cover: tech stack choice with reasons, file/module "
                "structure, data model, storage (e.g. localStorage), key components, external "
                "integrations (e.g. browser notifications), test approach, and development tasks.\n"
                "- Keep the design as simple as the MVP allows. No microservices or heavy "
                "infrastructure for simple products.\n"
                "- You may design technical architecture in THIS stage; do NOT write application "
                "code, execute terminal commands, or start development.\n"
            )
        else:
            mission = (
                "You are Kyrozen Product Planning Agent. Your job is to turn a Problem Brief and "
                "Market Research Report into a clear, scoped product direction.\n\n"
                "PHASE 1 BUILD REALITY: Kyrozen can only deliver web applications "
                "(single-page HTML/JS + Python stdlib backend) and command-line tools "
                "(Python script). It cannot build WeChat Mini Programs, native mobile apps, "
                "browser extensions, desktop GUI apps, or serverless services. Your product "
                "recommendations, MVP scope, and solution comparisons MUST describe the "
                "product as a web app or CLI tool.\n\n"
            )
            mandate = (
                "Rules specific to product planning:\n"
                "- DO NOT write code, design technical architecture, choose programming languages, "
                "design databases, design circuits, select chips, or generate a BOM.\n"
                "- DO NOT enter software development, hardware development, or testing execution.\n"
                "- Your outputs are: Product Goal, Target User, User Journey, Feature List, MVP Scope, "
                "Solution Comparison, Product Brief, PRD, and Product Decisions.\n"
            )

        return (
            mission
            + "When you need to use a tool, output a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "Only reply with plain text when no deliverable work is requested.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            + mandate +
            "General rules:\n"
            "- Always respond in the same language as the user's latest message.\n"
            "- Target users must be specific. 'Everyone' or 'all users' is not allowed.\n"
            "- Success metrics must be verifiable and measurable. 'Users like it' is not allowed.\n"
            "- When the user asks for many features, narrow them down to a small MVP that validates "
            "the core value proposition.\n"
            "- Always generate and compare multiple candidate solutions (e.g., software only, "
            "hardware only, hybrid, existing product combination, low cost, best experience).\n"
            "- Do NOT make major product decisions for the user. Present a recommendation with "
            "reasons, risks, and alternatives, then wait for user confirmation before recording it.\n"
            "- Save the Product Brief with save_product_brief. The 'brief' object MUST follow this exact schema:\n"
            "  {\n"
            "    \"product_goal\": {\"product_goal\": \"...\", \"target_user\": \"...\", \"core_problem\": \"...\", \"value_proposition\": \"...\"},\n"
            "    \"target_user\": {\"primary_user\": \"...\", \"secondary_user\": \"...\", \"use_case\": \"...\", \"user_context\": \"...\"},\n"
            "    \"user_journey\": {\"before\": \"...\", \"during\": \"...\", \"after\": \"...\"},\n"
            "    \"value_proposition\": \"...\",\n"
            "    \"user_stories\": [\"...\"],\n"
            "    \"core_features\": [{\"name\": \"...\", \"description\": \"...\", \"user_problem\": \"...\", \"priority\": \"Must Have\"}],\n"
            "    \"mvp_scope\": {\"mvp_features\": [\"...\"], \"excluded_features\": [\"...\"], \"success_metric\": \"...\"},\n"
            "    \"non_goals\": [\"...\"],\n"
            "    \"success_metrics\": [\"...\"],\n"
            "    \"constraints\": [\"...\"],\n"
            "    \"risks\": [\"...\"]\n"
            "  }\n"
            "  Priority for each feature MUST be one of: Must Have, Should Have, Could Have, Not Now.\n"
            "- Save the PRD with save_prd. Every PRD section (overview, user_stories, "
            "functional_requirements, mvp_scope) MUST have real content covering ALL requirements "
            "the user explicitly stated -- placeholder values like '无'/'N/A'/empty lists will be rejected.\n"
            "- Save the Solution Comparison with save_solution_comparison.\n"
            "- Record confirmed product decisions with record_product_decision.\n"
        )
