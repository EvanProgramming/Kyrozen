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
from kyrozen.logs import get_logger
from kyrozen.memory import InMemoryMemory, JsonFileMemory, ProjectMemory
from kyrozen.models import ModelInterface, get_model_provider
from kyrozen.project import KyrozenDatabase, ProjectContextBuilder, ProjectManager
from kyrozen.tools import get_default_registry


# Global state managed via lifespan
_agent: BaseAgent | None = None
_config: KyrozenConfig | None = None
_db: KyrozenDatabase | None = None
_project_manager: ProjectManager | None = None
_context_builder: ProjectContextBuilder | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    project_id: str | None = Field(None, description="Project ID to associate with this chat")
    confirmed: bool = Field(False, description="Whether to confirm high-risk actions")


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
        global _agent, _config, _db, _project_manager, _context_builder
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

        tools = get_default_registry(_project_manager)
        task_manager = TaskManager(db=_db)
        global _agent
        _agent = BaseAgent(
            config=_config,
            model=active_model,
            tools=tools,
            task_manager=task_manager,
            logger=logger,
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
            return {"task_id": task.id, "status": task.status, "project_id": request.project_id}
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

    return app


app = create_app()
