"""FastAPI web server and REST API for Kyrozen Core testing."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from kyrozen.config import KyrozenConfig, get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import TaskManager
from kyrozen.development.agent import SoftwareDevelopmentAgent
from kyrozen.discovery import ProblemDiscoveryAgent
from kyrozen.logs import get_logger
from kyrozen.memory import InMemoryMemory, JsonFileMemory, ProjectMemory
from kyrozen.models import ModelInterface, get_model_provider
from kyrozen.planning.agent import ProductPlanningAgent
from kyrozen.project import KyrozenDatabase, ProjectContextBuilder, ProjectManager
from kyrozen.research.agent import MarketResearchAgent
from kyrozen.tools import get_default_registry


# Global state managed via lifespan
_agent: BaseAgent | None = None
_discovery_agent: ProblemDiscoveryAgent | None = None
_research_agent: MarketResearchAgent | None = None
_planning_agent: ProductPlanningAgent | None = None
_development_agent: SoftwareDevelopmentAgent | None = None
_config: KyrozenConfig | None = None
_db: KyrozenDatabase | None = None
_project_manager: ProjectManager | None = None
_context_builder: ProjectContextBuilder | None = None


def _get_discovery_agent() -> ProblemDiscoveryAgent:
    if _discovery_agent is None:
        raise RuntimeError("Discovery agent not initialized")
    return _discovery_agent


def _get_research_agent() -> MarketResearchAgent:
    if _research_agent is None:
        raise RuntimeError("Research agent not initialized")
    return _research_agent


def _get_planning_agent() -> ProductPlanningAgent:
    if _planning_agent is None:
        raise RuntimeError("Planning agent not initialized")
    return _planning_agent


def _get_development_agent() -> SoftwareDevelopmentAgent:
    if _development_agent is None:
        raise RuntimeError("Development agent not initialized")
    return _development_agent


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    project_id: str | None = Field(None, description="Project ID to associate with this chat")
    confirmed: bool = Field(False, description="Whether to confirm high-risk actions")
    mode: str = Field("default", description="Chat mode: default, discovery, market_research, planning, or development")


class ConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Confirm and continue the waiting task")


class ToolExecuteRequest(BaseModel):
    tool: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    goal: str = ""
    initial_idea: str = ""


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    goal: str | None = None
    status: str | None = None
    current_stage: str | None = None
    next_steps: str | None = None
    risks: list[str] | None = None


class CreateDecisionRequest(BaseModel):
    decision: str = Field(..., min_length=1)
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)
    rejected_reasons: dict[str, str] = Field(default_factory=dict)


class CreateArtifactRequest(BaseModel):
    type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    content: str = ""
    change_reason: str = ""


def _get_agent() -> BaseAgent:
    if _agent is None:
        raise RuntimeError("Agent not initialized")
    return _agent


def _get_project_manager() -> ProjectManager:
    if _project_manager is None:
        raise RuntimeError("Project manager not initialized")
    return _project_manager


def _get_context_builder() -> ProjectContextBuilder:
    if _context_builder is None:
        raise RuntimeError("Context builder not initialized")
    return _context_builder


def _project_memory(project_id: str) -> ProjectMemory:
    if _config is None:
        raise RuntimeError("Config not initialized")
    os.makedirs(_config.project_dir(project_id), exist_ok=True)
    backend = JsonFileMemory(_config.project_memory_path(project_id))
    return ProjectMemory(project_id, backend)


def create_app(config: KyrozenConfig | None = None, model: ModelInterface | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _agent, _discovery_agent, _research_agent, _planning_agent, _development_agent, _config, _db, _project_manager, _context_builder
        _config = config or get_config()
        logger = get_logger(_config.log_level)
        issues = _config.validate()
        if issues:
            logger.error(f"Config issues: {'; '.join(issues)}")

        try:
            active_model = model if model is not None else get_model_provider(_config)
        except Exception as e:
            logger.error(f"Failed to initialize model provider: {e}")
            active_model = None

        _db = KyrozenDatabase(_config.db_path)
        _project_manager = ProjectManager(_db)
        _context_builder = ProjectContextBuilder(_project_manager, InMemoryMemory())

        tools = get_default_registry(
            _project_manager,
            tavily_api_key=_config.tavily_api_key,
            serper_api_key=_config.serper_api_key,
            github_token=_config.github_token,
            semantic_scholar_api_key=_config.semantic_scholar_api_key,
        )
        task_manager = TaskManager(db=_db)
        global _agent
        _agent = BaseAgent(
            config=_config,
            model=active_model,
            tools=tools,
            task_manager=task_manager,
            logger=logger,
        )
        global _discovery_agent
        _discovery_agent = ProblemDiscoveryAgent(
            config=_config,
            model=active_model,
            tools=tools,
            task_manager=task_manager,
            logger=logger,
            project_manager=_project_manager,
        )
        global _research_agent
        _research_agent = MarketResearchAgent(
            config=_config,
            model=active_model,
            tools=tools,
            task_manager=task_manager,
            logger=logger,
            project_manager=_project_manager,
        )
        global _planning_agent
        _planning_agent = ProductPlanningAgent(
            config=_config,
            model=active_model,
            tools=tools,
            task_manager=task_manager,
            logger=logger,
            project_manager=_project_manager,
        )
        global _development_agent
        _development_agent = SoftwareDevelopmentAgent(
            config=_config,
            model=active_model,
            tools=tools,
            task_manager=task_manager,
            logger=logger,
            project_manager=_project_manager,
        )
        logger.agent("Kyrozen Core API started")
        yield
        logger.agent("Kyrozen Core API shutting down")

    app = FastAPI(title="Kyrozen Core API", version="0.2.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Kyrozen Core</h1><p>Web UI not found.</p>")

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    @app.post("/api/chat")
    async def api_chat(request: ChatRequest):
        if request.mode == "discovery":
            agent = _get_discovery_agent()
        elif request.mode == "market_research":
            agent = _get_research_agent()
        elif request.mode == "planning":
            agent = _get_planning_agent()
        elif request.mode == "development":
            agent = _get_development_agent()
        else:
            agent = _get_agent()
        if agent.model is None:
            raise HTTPException(503, "Model provider not configured. Set DEEPSEEK_API_KEY or KYROZEN_API_KEY.")

        user_input = request.message
        if request.project_id:
            pm = _get_project_manager()
            project = pm.get(request.project_id)
            if project is None:
                raise HTTPException(404, f"Project '{request.project_id}' not found")
            builder = _get_context_builder()
            # Swap the context builder's memory backend to the project's memory file
            builder.memory = _project_memory(request.project_id)
            if request.mode == "discovery":
                context = builder.build_discovery_context(project)
            elif request.mode == "market_research":
                context = builder.build_research_context(project)
            elif request.mode == "planning":
                context = builder.build_planning_context(project)
            elif request.mode == "development":
                context = builder.build_development_context(project)
            else:
                context = builder.build(project)
            user_input = f"{context}\n{request.message}"
            # Ensure the agent uses the project's memory for this task
            agent.memory = _project_memory(request.project_id)
        else:
            # Use a global in-memory fallback if no project
            from kyrozen.memory import InMemoryMemory
            if not isinstance(agent.memory, InMemoryMemory):
                agent.memory = InMemoryMemory()

        try:
            task = agent.run(user_input, confirmed=request.confirmed, project_id=request.project_id)
            return {"task_id": task.id, "status": task.status, "project_id": request.project_id, "mode": request.mode}
        except Exception as e:
            raise HTTPException(500, f"Agent error: {e}")

    @app.get("/api/tasks/{task_id}")
    async def api_get_task(task_id: str):
        agent = _get_agent()
        task = agent.task_manager.get(task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        return task.to_dict()

    @app.post("/api/tasks/{task_id}/confirm")
    async def api_confirm_task(task_id: str, request: ConfirmRequest):
        agent = _get_agent()
        task = agent.task_manager.get(task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        if task.status != "waiting_confirmation":
            raise HTTPException(400, f"Task is not waiting for confirmation (status={task.status})")
        if not request.confirmed:
            task.fail("User declined the high-risk action")
            agent.task_manager.update(task)
            return task.to_dict()

        user_input = task.description
        if task.project_id:
            pm = _get_project_manager()
            project = pm.get(task.project_id)
            if project is not None:
                builder = _get_context_builder()
                builder.memory = _project_memory(task.project_id)
                user_input = f"{builder.build(project)}\n{task.description}"
            agent.memory = _project_memory(task.project_id)

        task.update_status("running")
        agent.task_manager.update(task)
        task = agent.run(user_input, confirmed=True, project_id=task.project_id)
        return task.to_dict()

    @app.get("/api/tasks")
    async def api_list_tasks(project_id: str | None = None):
        agent = _get_agent()
        return [task.to_dict() for task in agent.task_manager.list_tasks(project_id=project_id)]

    @app.get("/api/tools")
    async def api_list_tools():
        agent = _get_agent()
        return {"tools": agent.tools.list_schemas()}

    @app.post("/api/tools/execute")
    async def api_execute_tool(request: ToolExecuteRequest):
        agent = _get_agent()
        decision = agent.permission.check(request.tool, request.action, request.parameters)
        if not decision.allowed:
            raise HTTPException(403, decision.reason)
        result = agent.tools.execute(request.tool, request.action, request.parameters)
        return result.to_dict()

    @app.get("/api/health")
    async def api_health():
        return {
            "status": "ok" if _agent and _agent.model else "degraded",
            "provider": _config.provider if _config else None,
            "model": _config.model_simple if _config else None,
            "permission_mode": _config.permission_mode if _config else None,
        }

    @app.get("/api/config")
    async def api_config():
        if _config is None:
            raise HTTPException(503, "Config not loaded")
        return {
            "provider": _config.provider,
            "model_simple": _config.model_simple,
            "model_complex": _config.model_complex,
            "permission_mode": _config.permission_mode,
            "workspace_root": _config.workspace_root,
            "db_path": _config.db_path,
            "projects_dir": _config.projects_dir,
        }

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    @app.post("/api/projects")
    async def api_create_project(request: CreateProjectRequest):
        pm = _get_project_manager()
        project = pm.create(
            name=request.name,
            description=request.description,
            goal=request.goal,
            initial_idea=request.initial_idea,
        )
        # Ensure project directory and memory file exist
        if _config is not None:
            os.makedirs(_config.project_dir(project.id), exist_ok=True)
            _project_memory(project.id)
        return project.to_dict()

    @app.get("/api/projects")
    async def api_list_projects():
        pm = _get_project_manager()
        return [p.to_dict() for p in pm.list()]

    @app.get("/api/projects/{project_id}")
    async def api_get_project(project_id: str):
        pm = _get_project_manager()
        project = pm.get(project_id)
        if project is None:
            raise HTTPException(404, "Project not found")
        data = project.to_dict()
        data["recent_tasks"] = [t.to_dict() for t in pm.list_tasks(project_id)[:5]]
        data["recent_decisions"] = [d.to_dict() for d in pm.list_decisions(project_id)[:5]]
        data["recent_artifacts"] = [a.to_dict() for a in pm.list_artifacts(project_id)[:5]]
        return data

    @app.put("/api/projects/{project_id}")
    async def api_update_project(project_id: str, request: UpdateProjectRequest):
        pm = _get_project_manager()
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        project = pm.update(project_id, **updates)
        if project is None:
            raise HTTPException(404, "Project not found")
        return project.to_dict()

    @app.delete("/api/projects/{project_id}")
    async def api_archive_project(project_id: str):
        pm = _get_project_manager()
        project = pm.archive(project_id)
        if project is None:
            raise HTTPException(404, "Project not found")
        return project.to_dict()

    @app.get("/api/projects/{project_id}/tasks")
    async def api_project_tasks(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        return [t.to_dict() for t in pm.list_tasks(project_id)]

    @app.get("/api/projects/{project_id}/decisions")
    async def api_project_decisions(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        return [d.to_dict() for d in pm.list_decisions(project_id)]

    @app.post("/api/projects/{project_id}/decisions")
    async def api_create_decision(project_id: str, request: CreateDecisionRequest):
        pm = _get_project_manager()
        try:
            decision = pm.add_decision(
                project_id=project_id,
                decision=request.decision,
                reason=request.reason,
                alternatives=request.alternatives,
                rejected_reasons=request.rejected_reasons,
                source="user",
            )
            return decision.to_dict()
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/projects/{project_id}/artifacts")
    async def api_project_artifacts(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        return [a.to_dict() for a in pm.list_artifacts(project_id)]

    @app.post("/api/projects/{project_id}/artifacts")
    async def api_create_artifact(project_id: str, request: CreateArtifactRequest):
        pm = _get_project_manager()
        try:
            artifact = pm.save_artifact(
                project_id=project_id,
                type=request.type,
                title=request.title,
                content=request.content,
                change_reason=request.change_reason,
            )
            return artifact.to_dict()
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/projects/{project_id}/artifacts/{artifact_id}")
    async def api_get_artifact(project_id: str, artifact_id: str):
        pm = _get_project_manager()
        artifact = pm.get_artifact(project_id, artifact_id)
        if artifact is None:
            raise HTTPException(404, "Artifact not found")
        return artifact.to_dict()

    # ------------------------------------------------------------------
    # Problem Discovery
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/problem-discovery/state")
    async def api_discovery_state(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        from kyrozen.discovery.brief import ProblemBrief
        from kyrozen.discovery.question_engine import QuestionEngine

        latest = pm.get_latest_artifact(project_id, "problem_brief", title="Problem Brief")
        brief = ProblemBrief()
        if latest is not None:
            import json
            try:
                brief = ProblemBrief.from_dict(json.loads(latest.content))
            except (json.JSONDecodeError, ValueError):
                pass
        engine = QuestionEngine()
        summary = engine.state_summary(brief)
        return {
            "project_id": project_id,
            "brief": brief.to_dict(),
            "state_summary": summary,
            "latest_artifact_id": latest.id if latest else None,
        }

    # ------------------------------------------------------------------
    # Market Research
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/market-research/state")
    async def api_market_research_state(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        from kyrozen.research.models import MarketResearchReport

        latest_report = pm.get_latest_artifact(
            project_id, "market_research_report", title="Market Research Report"
        )
        report = MarketResearchReport()
        if latest_report is not None:
            import json
            try:
                report = MarketResearchReport.from_dict(json.loads(latest_report.content))
            except (json.JSONDecodeError, ValueError):
                pass

        sources = pm.list_artifacts(project_id)
        research_sources = [a for a in sources if a.type == "research_source"]
        decisions = [d for d in pm.list_decisions(project_id) if d.decision.startswith("Opportunity decision:")]

        return {
            "project_id": project_id,
            "report": report.to_dict(),
            "source_count": len(research_sources),
            "sources": [a.to_dict() for a in research_sources[-10:]],
            "decisions": [d.to_dict() for d in decisions[-5:]],
            "latest_report_artifact_id": latest_report.id if latest_report else None,
        }

    # ------------------------------------------------------------------
    # Product Planning
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/planning/state")
    async def api_planning_state(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        from kyrozen.planning.models import PRD, ProductBrief, SolutionComparison

        latest_brief = pm.get_latest_artifact(project_id, "product_brief", title="Product Brief")
        brief = ProductBrief()
        if latest_brief is not None:
            import json
            try:
                brief = ProductBrief.from_dict(json.loads(latest_brief.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_prd = pm.get_latest_artifact(project_id, "prd", title="Product Requirements Document")
        prd = PRD()
        if latest_prd is not None:
            import json
            try:
                prd = PRD.from_dict(json.loads(latest_prd.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_comparison = pm.get_latest_artifact(
            project_id, "solution_comparison", title="Solution Comparison"
        )
        comparison = SolutionComparison()
        if latest_comparison is not None:
            import json
            try:
                comparison = SolutionComparison.from_dict(json.loads(latest_comparison.content))
            except (json.JSONDecodeError, ValueError):
                pass

        decisions = [d for d in pm.list_decisions(project_id) if d.decision.startswith("Product decision:")]

        return {
            "project_id": project_id,
            "brief": brief.to_dict(),
            "prd": prd.to_dict(),
            "solution_comparison": comparison.to_dict(),
            "decisions": [d.to_dict() for d in decisions[-5:]],
            "latest_brief_artifact_id": latest_brief.id if latest_brief else None,
            "latest_prd_artifact_id": latest_prd.id if latest_prd else None,
            "latest_comparison_artifact_id": latest_comparison.id if latest_comparison else None,
        }

    # ------------------------------------------------------------------
    # Software Development
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/development/state")
    async def api_development_state(project_id: str):
        pm = _get_project_manager()
        if pm.get(project_id) is None:
            raise HTTPException(404, "Project not found")
        from kyrozen.development.models import (
            DeploymentGuide,
            FeatureImplementation,
            TechnicalPlan,
            TestReport,
        )

        latest_plan = pm.get_latest_artifact(project_id, "technical_plan", title="Technical Plan")
        plan = TechnicalPlan()
        if latest_plan is not None:
            import json
            try:
                plan = TechnicalPlan.from_dict(json.loads(latest_plan.content))
            except (json.JSONDecodeError, ValueError):
                pass

        feature_records = []
        for artifact in pm.list_artifacts(project_id):
            if artifact.type == "feature_implementation_record":
                try:
                    feature_records.append(
                        FeatureImplementation.from_dict(json.loads(artifact.content))
                    )
                except (json.JSONDecodeError, ValueError):
                    pass

        latest_report = pm.get_latest_artifact(project_id, "test_report", title="Test Report")
        report = TestReport()
        if latest_report is not None:
            import json
            try:
                report = TestReport.from_dict(json.loads(latest_report.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_guide = pm.get_latest_artifact(
            project_id, "deployment_guide", title="Deployment Guide"
        )
        guide = DeploymentGuide()
        if latest_guide is not None:
            import json
            try:
                guide = DeploymentGuide.from_dict(json.loads(latest_guide.content))
            except (json.JSONDecodeError, ValueError):
                pass

        decisions = [
            d for d in pm.list_decisions(project_id)
            if d.decision.startswith("Development decision:")
        ]

        # Summarize git commits if software project exists
        import subprocess
        from pathlib import Path

        git_log: list[str] = []
        if _config is not None:
            software_dir = Path(_config.project_dir(project_id)) / "software"
            if (software_dir / ".git").exists():
                try:
                    result = subprocess.run(
                        ["git", "-C", str(software_dir), "log", "--oneline", "-10"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        git_log = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                except Exception:
                    pass

        return {
            "project_id": project_id,
            "technical_plan": plan.to_dict(),
            "feature_records": [r.to_dict() for r in feature_records],
            "test_report": report.to_dict(),
            "deployment_guide": guide.to_dict(),
            "decisions": [d.to_dict() for d in decisions[-5:]],
            "git_log": git_log,
            "latest_plan_artifact_id": latest_plan.id if latest_plan else None,
            "latest_report_artifact_id": latest_report.id if latest_report else None,
            "latest_guide_artifact_id": latest_guide.id if latest_guide else None,
        }

    return app


app = create_app()
