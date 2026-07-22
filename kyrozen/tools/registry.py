"""Tool registry for Kyrozen Core."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolResult, ToolSchema
from typing import TYPE_CHECKING

from .file_tools import FileReadTool, FileWriteTool, ListDirTool, FindFilesTool
from .terminal_tools import TerminalTool
from .git_tools import GitTool

if TYPE_CHECKING:
    from kyrozen.project.manager import ProjectManager


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def list_schemas(self) -> list[dict[str, Any]]:
        return [tool.schema.to_dict() for tool in self._tools.values()]

    def execute(self, name: str, action: str, parameters: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, data=None, error=f"Tool '{name}' not found")
        return tool.execute(action, parameters)


def get_default_registry(
    project_manager: "ProjectManager | None" = None,
    tavily_api_key: str | None = None,
    serper_api_key: str | None = None,
    github_token: str | None = None,
    semantic_scholar_api_key: str | None = None,
) -> ToolRegistry:
    """Return a registry with Phase 1-7 tools pre-registered."""
    from .development_tools import (
        RecordDevelopmentDecisionTool,
        SaveDeploymentGuideTool,
        SaveFeatureImplementationTool,
        SaveTechnicalPlanTool,
        SaveTestReportTool,
    )
    from .hardware_tools import (
        HardwareBridgeTool,
        RecordHardwareDecisionTool,
        SaveAssemblyStepTool,
        SaveBOMTool,
        SaveComponentTool,
        SaveDebugRecordTool,
        SaveFirmwareProjectTool,
        SaveHardwareArchitectureTool,
        SaveWiringDesignTool,
        UpdatePurchaseStatusTool,
    )
    from .discovery_tools import (
        AssessConfidenceTool,
        RecordEvidenceTool,
        RecordProblemDecisionTool,
        SaveProblemBriefTool,
    )
    from .planning_tools import (
        RecordProductDecisionTool,
        SavePRDTool,
        SaveProductBriefTool,
        SaveSolutionComparisonTool,
    )
    from .project_tools import RecordDecisionTool, UpdateProjectTool
    from .research.tools import (
        GitHubSearchTool,
        PaperSearchTool,
        RecordOpportunityDecisionTool,
        SaveMarketResearchReportTool,
        SaveResearchSourceTool,
        WebSearchTool,
    )

    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(ListDirTool())
    registry.register(FindFilesTool())
    registry.register(TerminalTool())
    registry.register(GitTool())
    registry.register(UpdateProjectTool(project_manager))
    registry.register(RecordDecisionTool(project_manager))
    registry.register(SaveProblemBriefTool(project_manager))
    registry.register(RecordEvidenceTool(project_manager))
    registry.register(AssessConfidenceTool(project_manager))
    registry.register(RecordProblemDecisionTool(project_manager))
    registry.register(WebSearchTool(tavily_api_key=tavily_api_key, serper_api_key=serper_api_key))
    registry.register(GitHubSearchTool(token=github_token))
    registry.register(PaperSearchTool(api_key=semantic_scholar_api_key))
    registry.register(SaveResearchSourceTool(project_manager))
    registry.register(SaveMarketResearchReportTool(project_manager))
    registry.register(RecordOpportunityDecisionTool(project_manager))
    registry.register(SaveProductBriefTool(project_manager))
    registry.register(SavePRDTool(project_manager))
    registry.register(SaveSolutionComparisonTool(project_manager))
    registry.register(RecordProductDecisionTool(project_manager))
    registry.register(SaveTechnicalPlanTool(project_manager))
    registry.register(SaveFeatureImplementationTool(project_manager))
    registry.register(SaveTestReportTool(project_manager))
    registry.register(SaveDeploymentGuideTool(project_manager))
    registry.register(RecordDevelopmentDecisionTool(project_manager))
    registry.register(SaveHardwareArchitectureTool(project_manager))
    registry.register(SaveComponentTool(project_manager))
    registry.register(SaveBOMTool(project_manager))
    registry.register(UpdatePurchaseStatusTool(project_manager))
    registry.register(SaveWiringDesignTool(project_manager))
    registry.register(SaveFirmwareProjectTool(project_manager))
    registry.register(RecordHardwareDecisionTool(project_manager))
    registry.register(SaveAssemblyStepTool(project_manager))
    registry.register(SaveDebugRecordTool(project_manager))
    registry.register(HardwareBridgeTool(project_manager))
    return registry
