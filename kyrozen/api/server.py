"""FastAPI web server and REST API for Kyrozen Core testing."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from kyrozen.config import KyrozenConfig, get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import TaskManager
from kyrozen.logs import get_logger
from kyrozen.models import ModelInterface, get_model_provider
from kyrozen.tools import get_default_registry


# Global state managed via lifespan
_agent: BaseAgent | None = None
_config: KyrozenConfig | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    confirmed: bool = Field(False, description="Whether to confirm high-risk actions")


class ConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Confirm and continue the waiting task")


class ToolExecuteRequest(BaseModel):
    tool: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


def _get_agent() -> BaseAgent:
    if _agent is None:
        raise RuntimeError("Agent not initialized")
    return _agent


def create_app(config: KyrozenConfig | None = None, model: ModelInterface | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _agent, _config
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

        tools = get_default_registry()
        task_manager = TaskManager(store_path=_config.task_store_path)
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

    app = FastAPI(title="Kyrozen Core API", version="0.1.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Kyrozen Core</h1><p>Web UI not found.</p>")

    @app.post("/api/chat")
    async def api_chat(request: ChatRequest):
        agent = _get_agent()
        if agent.model is None:
            raise HTTPException(503, "Model provider not configured. Set DEEPSEEK_API_KEY or KYROZEN_API_KEY.")
        try:
            task = agent.run(request.message, confirmed=request.confirmed)
            return {"task_id": task.id, "status": task.status}
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
        # Re-run with confirmed=True using original description
        task.update_status("running")
        agent.task_manager.update(task)
        task = agent.run(task.description, confirmed=True)
        return task.to_dict()

    @app.get("/api/tasks")
    async def api_list_tasks():
        agent = _get_agent()
        return [task.to_dict() for task in agent.task_manager.list_tasks()]

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
        }

    return app


app = create_app()
