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
        # GATE HONESTY: only auto-confirm the research when the report carries
        # real external evidence (clickable http(s) sources). A report that says
        # "搜索失败 / 无结果" must NOT silently satisfy the gate -- the user has to
        # confirm it manually (or configure the search service and retry).
        has_evidence = self._has_external_evidence(report)
        result["external_evidence"] = has_evidence
        quality_warning = self._source_quality_warning(report)
        if quality_warning:
            result["quality_warning"] = quality_warning
        if workspace and result.get("file"):
            try:
                from kyrozen.core.stagegate import record_report_deliverable

                if has_evidence:
                    record_report_deliverable(workspace, "market_report", "market_confirmed")
                else:
                    # File was written, so the deliverable IS detected; only the
                    # user-confirmation gate is held back until real evidence exists.
                    record_report_deliverable(
                        workspace,
                        "market_report",
                        "market_confirmed",
                        auto_confirm=False,
                    )
            except Exception:
                pass
            if not has_evidence:
                result["warning"] = (
                    "报告中没有任何外部证据链接（http/https 来源），未自动确认市场调研门禁。"
                    "请配置搜索服务后重新调研，或由用户在进度面板手动确认。"
                )
        return ToolResult(success=True, data=result)

    @staticmethod
    def _has_external_evidence(report) -> bool:
        """True when the report contains at least one real http(s) source URL."""
        import re
        data = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        blob = json.dumps(data, ensure_ascii=False)
        return bool(re.search(r"https?://[^\s\"']{8,}", blob))

    @staticmethod
    def _source_quality_warning(report) -> str | None:
        """Return a warning string if the research sources look untrustworthy.

        P0-R5 / P1-R5: competitors like Listonic, OurGroceries, and Bring! all
        pointing to the same YouTube URL is a red flag (model hallucination).
        We flag reports where all external URLs come from a single domain, or
        where multiple competitors share the exact same source URL.
        """
        import re
        from urllib.parse import urlparse

        competitors = getattr(report, "competitors", []) or []
        if not competitors:
            return None
        all_urls: list[str] = []
        for c in competitors:
            sources = getattr(c, "sources", []) or []
            for src in sources:
                if isinstance(src, str) and src.startswith("http"):
                    all_urls.append(src)
        if len(all_urls) < 2:
            return None  # not enough data to judge
        domains = set()
        for url in all_urls:
            try:
                domains.add(urlparse(url).netloc)
            except Exception:
                domains.add(url)
        if len(domains) == 1:
            return f"所有竞品链接都指向同一域名 ({list(domains)[0]})，搜索结果可能不可信，建议用中文搜索词重新调研。"
        # Also check if any two competitors share ALL their source URLs exactly.
        seen_sets: dict[frozenset[str], list[str]] = {}
        for c in competitors:
            c_sources = frozenset(s for s in (getattr(c, "sources", []) or []) if isinstance(s, str) and s.startswith("http"))
            if c_sources:
                seen_sets.setdefault(c_sources, []).append(c.name)
        for src_set, names in seen_sets.items():
            if len(names) >= 2 and len(src_set) >= 1:
                return f"以下竞品共享完全相同的来源链接：{'、'.join(names[:4])}（链接数={len(src_set)}），搜索结果质量存疑。"
        return None

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
