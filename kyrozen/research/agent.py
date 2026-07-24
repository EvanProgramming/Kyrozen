"""Market Research Agent for Kyrozen Phase 4.

The agent receives a Problem Brief and produces a Market Research Report,
using real external search tools and rigorous source tracking.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from kyrozen.core.agent import BaseAgent

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class MarketResearchAgent(BaseAgent):
    """Agent specialized in market research and opportunity evaluation."""

    max_rounds = 12

    def __init__(self, *args: Any, project_manager: "ProjectManager | None" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Market Research Agent. Your job is to evaluate whether the "
            "problem described in the Problem Brief is worth solving, using real market evidence.\n\n"
            "IMPORTANT: Start immediately. Do not just plan or describe what you will do. "
            "Your first response must be a web_search tool call.\n\n"
            "When you need to use a tool, output ONLY a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "If no tool is needed, reply with a plain text answer.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "Rules:\n"
            "- DO NOT design a product, write a PRD/MVP, recommend hardware, or write code.\n"
            "- DO NOT make up companies, products, user numbers, or market sizes.\n"
            "- If no evidence is found, explicitly say \"Insufficient evidence\".\n"
            "- Always save the source URL, access_date, and confidence for every external claim.\n"
            "- Distinguish Fact, Inference, and Unknown in every source item.\n"
            "- Analyze competitors honestly: include why they succeed and why they fail.\n"
            "- Search for: existing products/apps, open source projects, academic papers, patents, community discussions, alternative solutions. Use at most 4 searches.\n"
            "- After each search, save important sources with save_research_source. Do not rely on memory; save every source immediately.\n"
            "- After saving sources, you MUST call save_market_research_report to persist the final report.\n"
            "  The report object MUST use this exact schema:\n"
            "  {\n"
            "    \"problem_summary\": \"string\",\n"
            "    \"market_status\": \"string (market size, trends, maturity)\",\n"
            "    \"competitors\": [{\"name\": \"string\", \"company\": \"string\", \"solution\": \"string\", \"target_user\": \"string\", \"main_features\": [\"string\"], \"price\": \"string\", \"advantages\": [\"string\"], \"complaints\": [\"string\"], \"failure_reason\": \"string\", \"sources\": [\"string\"]}],\n"
            "    \"open_source_projects\": [{\"title\", \"url\", \"source_type\", \"summary\", \"related_claim\", \"confidence\", \"fact_type\"}],\n"
            "    \"user_feedback\": [{same schema as open_source_projects}],\n"
            "    \"alternative_solutions\": [{same schema as open_source_projects}],\n"
            "    \"technology_routes\": [\"string\"],\n"
            "    \"market_gap\": {\"existing_solution\": \"string\", \"problem_remaining\": \"string\", \"possible_difference\": \"string\", \"risk\": \"string\", \"confidence\": \"low|medium|high\"},\n"
            "    \"risks\": [\"string\"],\n"
            "    \"recommendation\": \"One of: continue_development, narrow_scope, change_target_user, change_product_form, use_existing_solution, pause, abandon\",\n"
            "    \"sources\": [{same schema as open_source_projects}]\n"
            "  }\n"
            "- Then record the opportunity decision with record_opportunity_decision.\n"
            "- Do not exceed the tool-call budget: leave enough rounds for save_research_source, save_market_research_report, and record_opportunity_decision.\n"
            "- If existing solutions are good enough, recommend \"use_existing_solution\" or \"abandon\".\n"
            "- After calling any tool, wait for the tool result and then summarize it in natural language. NEVER output raw JSON to the user.\n"
            "- NEVER output internal planning text such as 'Now let me search', 'Search X:', or 'Next I will' to the user. Only output the final summary or the tool JSON.\n"
            "- When a search returns no results or fails, say so clearly instead of fabricating sources.\n"
            "- Respond in the same language as the user's request (Chinese if the user writes in Chinese).\n"
            "- The final answer must be a concise summary covering: market status, key competitors/open-source alternatives, user pain points, and a recommendation.\n"
        )

    def build_research_context(
        self,
        project_id: str,
        problem_brief: dict[str, Any] | None = None,
        previous_report: dict[str, Any] | None = None,
    ) -> str:
        """Build the context block injected before the user's message."""
        lines = ["[Market Research Context]"]
        lines.append(f"Project ID: {project_id}")
        lines.append(
            "Your role: Evaluate whether the problem is worth solving. "
            "Do not design products or recommend technology.\n"
        )

        lines.append("[Problem Brief]")
        if problem_brief:
            for key, value in problem_brief.items():
                if key == "unknown_assumptions":
                    if value:
                        lines.append(f"  {key}:")
                        for item in value:
                            lines.append(
                                f"    - {item.get('claim', '')} (source: {item.get('source', '')}, verified: {item.get('verified', False)})"
                            )
                    else:
                        lines.append(f"  {key}: none")
                else:
                    display_value = value if value else "(not set)"
                    lines.append(f"  {key}: {display_value}")
        else:
            lines.append("  (no problem brief available)")

        if previous_report:
            lines.append("\n[Previous Market Research Report]")
            lines.append(f"  recommendation: {previous_report.get('recommendation', 'none')}")
            lines.append(f"  market_status: {previous_report.get('market_status', 'none')}")

        lines.append("\n[User Message]")
        return "\n".join(lines)
