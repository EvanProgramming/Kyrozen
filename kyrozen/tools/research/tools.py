"""Kyrozen Tool wrappers for Phase 4 market research.

These tools expose search, source saving, report saving, and decision recording
to the Market Research Agent through the standard Tool interface.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

from kyrozen.research.models import (
    OPPORTUNITY_DECISIONS,
    Competitor,
    MarketGap,
    MarketResearchReport,
    ResearchSource,
)

from ..base import Tool, ToolParameter, ToolResult, ToolSchema
from .providers import GitHubSearchProvider, SemanticScholarProvider, get_default_search_provider

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class WebSearchTool(Tool):
    """Search the web for products, apps, companies, and general information."""

    def __init__(self, tavily_api_key: str | None = None, serper_api_key: str | None = None) -> None:
        self.name = "web_search"
        self.description = "Search the web for real market information. Returns sources with URLs."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "search": [
                    ToolParameter(name="query", param_type="string", description="Search query"),
                    ToolParameter(name="limit", param_type="integer", description="Max results", required=False),
                ]
            },
        )
        self.provider = get_default_search_provider(tavily_api_key, serper_api_key)

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if action != "search":
            return ToolResult(success=False, data=None, error=f"Action '{action}' not supported")
        query = parameters.get("query", "")
        if not query:
            return ToolResult(success=False, data=None, error="Missing query")
        limit = int(parameters.get("limit", 5))
        sources = self.provider.search(query, limit=limit)
        return ToolResult(success=True, data={"sources": [s.to_dict() for s in sources]})


class GitHubSearchTool(Tool):
    """Search GitHub for open source projects related to the problem."""

    def __init__(self, token: str | None = None) -> None:
        self.name = "search_github"
        self.description = "Search GitHub repositories for open source projects."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "search": [
                    ToolParameter(name="query", param_type="string", description="Search query"),
                    ToolParameter(name="limit", param_type="integer", description="Max results", required=False),
                ]
            },
        )
        self.provider = GitHubSearchProvider(token=token)

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if action != "search":
            return ToolResult(success=False, data=None, error=f"Action '{action}' not supported")
        query = parameters.get("query", "")
        if not query:
            return ToolResult(success=False, data=None, error="Missing query")
        limit = int(parameters.get("limit", 5))
        sources = self.provider.search(query, limit=limit)
        return ToolResult(success=True, data={"sources": [s.to_dict() for s in sources]})


class PaperSearchTool(Tool):
    """Search academic papers via Semantic Scholar."""

    def __init__(self, api_key: str | None = None) -> None:
        self.name = "search_papers"
        self.description = "Search academic papers for research and technology routes."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "search": [
                    ToolParameter(name="query", param_type="string", description="Search query"),
                    ToolParameter(name="limit", param_type="integer", description="Max results", required=False),
                ]
            },
        )
        self.provider = SemanticScholarProvider(api_key=api_key)

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if action != "search":
            return ToolResult(success=False, data=None, error=f"Action '{action}' not supported")
        query = parameters.get("query", "")
        if not query:
            return ToolResult(success=False, data=None, error="Missing query")
        limit = int(parameters.get("limit", 5))
        sources = self.provider.search(query, limit=limit)
        return ToolResult(success=True, data={"sources": [s.to_dict() for s in sources]})


class SaveResearchSourceTool(Tool):
    """Save a research source as a project artifact."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_research_source"
        self.description = "Save an external research source to the project workspace."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="source", param_type="object", description="ResearchSource as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        source_data = parameters.get("source", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            source = ResearchSource.from_dict(source_data)
            content = json.dumps(source.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="research_source",
                title=f"Source: {source.title[:40]}",
                content=content,
                change_reason="New research source",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "source": source.to_dict()})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveMarketResearchReportTool(Tool):
    """Save the final Market Research Report and materialize it as the stage-gate
    deliverable file docs/MARKET.md so the local progress gate detects it."""

    def __init__(self, project_manager: "ProjectManager | None" = None, config: Any = None) -> None:
        self.project_manager = project_manager
        self.config = config
        self.name = "save_market_research_report"
        self.description = "Save or update the Market Research Report and write it to docs/MARKET.md."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="report", param_type="object", description="MarketResearchReport as JSON object"),
                ]
            },
        )

    @staticmethod
    def _resolve_workspace(project_id, project_manager, config):
        # Server: a ProjectManager is present, so the workspace is the
        # project-scoped directory (config.project_dir). On the desktop the
        # ProjectManager is None and config.workspace_root points directly at
        # the user-selected workspace (set per-task in desktop main.py).
        if project_manager is not None and project_id and hasattr(config, "project_dir"):
            try:
                return str(config.project_dir(project_id))
            except Exception:
                pass
        ws = getattr(config, "workspace_root", None)
        if ws and Path(ws).is_absolute():
            return str(ws)
        return None

    @staticmethod
    def _render_markdown(report):
        data = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        lines = ["# Market Research Report", ""]
        for key, value in data.items():
            if value is None or value == "" or value == [] or value == {}:
                continue
            title = key.replace("_", " ").title()
            lines.append("## " + title)
            if isinstance(value, (list, dict)):
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(value, ensure_ascii=False, indent=2))
                lines.append("```")
            else:
                lines.append("")
                lines.append(str(value))
            lines.append("")
        return chr(10).join(lines)

    def _execute(self, action, parameters):
        project_id = parameters.get("project_id")
        report_data = parameters.get("report", {})
        if not report_data:
            return ToolResult(success=False, data=None, error="Missing report")
        try:
            report = MarketResearchReport.from_dict(report_data)
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
        content = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        result = {}
        if self.project_manager is not None and project_id:
            try:
                artifact = self.project_manager.save_artifact(
                    project_id=project_id,
                    type="market_research_report",
                    title="Market Research Report",
                    content=content,
                    change_reason="Market research update",
                )
                result["artifact_id"] = artifact.id
                result["version"] = artifact.version
            except Exception as exc:
                logger.debug("save_artifact failed: %s", exc)
        workspace = self._resolve_workspace(project_id or "", self.project_manager, self.config)
        if workspace:
            try:
                out = Path(workspace) / "docs" / "MARKET.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(self._render_markdown(report), encoding="utf-8")
                result["file"] = str(out)
            except Exception as exc:
                logger.debug("write MARKET.md failed: %s", exc)
        if not result:
            return ToolResult(success=False, data=None, error="无法保存调研报告：未找到可写的项目工作区。")
        return ToolResult(success=True, data=result)

class RecordOpportunityDecisionTool(Tool):
    """Record the final opportunity decision from market research."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_opportunity_decision"
        self.description = "Record an opportunity decision based on market research."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(
                        name="decision",
                        param_type="string",
                        description=f"One of: {', '.join(sorted(OPPORTUNITY_DECISIONS))}",
                    ),
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
        if decision not in OPPORTUNITY_DECISIONS:
            return ToolResult(success=False, data=None, error=f"Invalid decision '{decision}'")
        try:
            recorded = self.project_manager.add_decision(
                project_id=project_id,
                decision=f"Opportunity decision: {decision}",
                reason=reason,
                source="agent",
            )
            return ToolResult(success=True, data={"decision_id": recorded.id, "decision": decision})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))
