"""FastAPI web server and REST API for Kyrozen Core testing."""

from __future__ import annotations

import json
import os
import shutil
from contextlib import asynccontextmanager
import traceback
import uuid
from pathlib import Path
from typing import Any

import asyncio
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from supabase import create_client

from kyrozen.auth.context import current_user_ctx
from kyrozen.auth.dependencies import CurrentUser, get_current_user, get_current_user_optional, require_admin
from kyrozen.config import KyrozenConfig, get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import TaskManager
from kyrozen.development.agent import SoftwareDevelopmentAgent
from kyrozen.discovery import ProblemDiscoveryAgent
from kyrozen.hardware.agent import HardwareDevelopmentAgent
from kyrozen.logs import get_logger
from kyrozen.memory import InMemoryMemory, JsonFileMemory, ProjectMemory
from kyrozen.models import ModelInterface, get_model_provider
from kyrozen.planning.agent import ProductPlanningAgent
from kyrozen.project import KyrozenDatabase, ProjectContextBuilder, ProjectManager, SupabaseDatabase, create_database
from kyrozen.project.project import PROJECT_STAGES
from kyrozen.research.agent import MarketResearchAgent
from kyrozen.testing.agent import TestingAgent
from kyrozen.learning.agent import LearningAgent
from kyrozen.learning.repository import LearningRepository
from kyrozen.tools import get_default_registry


# Global state managed via lifespan
_agent_factory: "AgentFactory | None" = None
_config: KyrozenConfig | None = None
_db: KyrozenDatabase | SupabaseDatabase | None = None
_project_manager: ProjectManager | None = None
_context_builder: ProjectContextBuilder | None = None
_learning_repository: LearningRepository | None = None


class AgentFactory:
    """Create request-scoped agent instances with isolated in-memory state."""

    def __init__(
        self,
        config: KyrozenConfig,
        model: ModelInterface | None,
        db: KyrozenDatabase | SupabaseDatabase,
        project_manager: ProjectManager,
        learning_repository: LearningRepository,
        logger: Any,
    ) -> None:
        self.config = config
        self.model = model
        self.db = db
        self.project_manager = project_manager
        self.learning_repository = learning_repository
        self.logger = logger
        self.tools = get_default_registry(
            project_manager,
            memory=InMemoryMemory(),
            learning_repository=learning_repository,
            tavily_api_key=config.tavily_api_key,
            serper_api_key=config.serper_api_key,
            github_token=config.github_token,
            semantic_scholar_api_key=config.semantic_scholar_api_key,
        )

    def _task_manager(self) -> TaskManager:
        return TaskManager(db=self.db, logger=self.logger)

    def create_base_agent(self) -> BaseAgent:
        return BaseAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
        )

    def create_discovery_agent(self) -> ProblemDiscoveryAgent:
        return ProblemDiscoveryAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
            project_manager=self.project_manager,
        )

    def create_research_agent(self) -> MarketResearchAgent:
        return MarketResearchAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
            project_manager=self.project_manager,
        )

    def create_planning_agent(self) -> ProductPlanningAgent:
        return ProductPlanningAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
            project_manager=self.project_manager,
        )

    def create_development_agent(self) -> SoftwareDevelopmentAgent:
        return SoftwareDevelopmentAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
            project_manager=self.project_manager,
        )

    def create_hardware_agent(self) -> HardwareDevelopmentAgent:
        return HardwareDevelopmentAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
            project_manager=self.project_manager,
        )

    def create_testing_agent(self) -> TestingAgent:
        return TestingAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=InMemoryMemory(),
            logger=self.logger,
            project_manager=self.project_manager,
        )

    def create_learning_agent(self) -> LearningAgent:
        return LearningAgent(
            config=self.config,
            model=self.model,
            tools=self.tools,
            task_manager=self._task_manager(),
            memory=self.learning_repository,
            logger=self.logger,
            project_manager=self.project_manager,
        )


def _get_agent_factory() -> AgentFactory:
    if _agent_factory is None:
        raise RuntimeError("Agent factory not initialized")
    return _agent_factory


def _get_discovery_agent() -> ProblemDiscoveryAgent:
    return _get_agent_factory().create_discovery_agent()


def _get_research_agent() -> MarketResearchAgent:
    return _get_agent_factory().create_research_agent()


def _get_planning_agent() -> ProductPlanningAgent:
    return _get_agent_factory().create_planning_agent()


def _get_development_agent() -> SoftwareDevelopmentAgent:
    return _get_agent_factory().create_development_agent()


def _get_hardware_agent() -> HardwareDevelopmentAgent:
    return _get_agent_factory().create_hardware_agent()


def _get_testing_agent() -> TestingAgent:
    return _get_agent_factory().create_testing_agent()


def _get_learning_agent() -> LearningAgent:
    return _get_agent_factory().create_learning_agent()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    project_id: str | None = Field(None, description="Project ID to associate with this chat")
    confirmed: bool = Field(False, description="Whether to confirm high-risk actions")
    mode: str = Field("default", description="Chat mode: default, discovery, market_research, planning, development, hardware, testing, or learning")
    stream: bool = Field(False, description="Stream task progress via Server-Sent Events")


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    name: str | None = None


class SigninRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


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


class CreateFeedbackRequest(BaseModel):
    type: str = Field(..., pattern="^(bug|feature_request|experience|ai_suggestion)$")
    description: str = Field(..., min_length=1)
    project_id: str | None = None
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")


class CreateEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class CreateLearningRecordRequest(BaseModel):
    memory: str = Field(..., min_length=1)
    memory_type: str = Field(..., pattern="^(user_preference|user_capability|project_fact|product_decision|validated_success|validated_failure|external_knowledge)$")
    source: str = ""
    confidence: str = Field("low", pattern="^(low|medium|high)$")
    verification_status: str = Field("unverified", pattern="^(unverified|user_provided|externally_verified|experiment_verified|repeatedly_verified)$")
    scope: str = Field("private", pattern="^(private|user|public)$")
    tags: list[str] = Field(default_factory=list)


class CreateFailureKnowledgeRequest(BaseModel):
    problem: str = Field(..., min_length=1)
    cause: str = Field(..., min_length=1)
    solution: str = Field(..., min_length=1)
    affected_scope: str = ""
    verification: str = ""
    confidence: str = Field("low", pattern="^(low|medium|high)$")
    verification_status: str = Field("unverified", pattern="^(unverified|user_provided|externally_verified|experiment_verified|repeatedly_verified)$")


class CreateSuccessKnowledgeRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    solution: str = Field(..., min_length=1)
    conditions: list[str] = Field(default_factory=list)
    result: str = ""
    confidence: str = Field("low", pattern="^(low|medium|high)$")
    verification_status: str = Field("unverified", pattern="^(unverified|user_provided|externally_verified|experiment_verified|repeatedly_verified)$")


class CreateSuggestionRequest(BaseModel):
    suggestion: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    evidence: list[str] = Field(default_factory=list)
    impact: str = ""
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")
    status: str = Field("new", pattern="^(new|accepted|rejected|later|ignored)$")
    category: str = Field("", pattern="^(|scope_drift|unverified_assumption|cost_optimization|tech_risk|test_gap|new_opportunity)$")
    related_learning_ids: list[str] = Field(default_factory=list)


class UpdateSuggestionStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(new|accepted|rejected|later|ignored)$")


class AnalyticsSummaryResponse(BaseModel):
    total_events: int
    events_by_type: dict[str, int]
    unique_users: int
    total_feedback: int
    feedback_by_type: dict[str, int]


def _get_agent() -> BaseAgent:
    return _get_agent_factory().create_base_agent()


def _get_project_manager() -> ProjectManager:
    if _project_manager is None:
        raise RuntimeError("Project manager not initialized")
    return _project_manager


def _get_context_builder() -> ProjectContextBuilder:
    if _context_builder is None:
        raise RuntimeError("Context builder not initialized")
    return _context_builder


def _get_learning_repository() -> LearningRepository:
    if _learning_repository is None:
        raise RuntimeError("Learning repository not initialized")
    return _learning_repository


def _project_memory(project_id: str) -> ProjectMemory:
    if _config is None:
        raise RuntimeError("Config not initialized")
    os.makedirs(_config.project_dir(project_id), exist_ok=True)
    backend = JsonFileMemory(_config.project_memory_path(project_id))
    return ProjectMemory(project_id, backend)


def _get_owned_project(
    project_id: str,
    current_user: CurrentUser,
) -> Any:
    """Fetch a project and enforce user ownership."""
    pm = _get_project_manager()
    project = pm.get(project_id)
    if project is None or project.user_id != current_user.user_id:
        raise HTTPException(404, "Project not found")
    return project


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _recommend_next_action(project: Any) -> dict[str, str] | None:
    """Recommend the next action based on the project's current stage."""
    mapping = {
        "problem_discovery": {
            "action": "和 AI 一起澄清问题",
            "reason": "项目刚创建，需要先理解问题",
            "target_mode": "discovery",
        },
        "market_research": {
            "action": "进行市场调研",
            "reason": "问题明确后需要了解市场",
            "target_mode": "market_research",
        },
        "product_definition": {
            "action": "规划产品定义",
            "reason": "基于调研结果定义产品",
            "target_mode": "planning",
        },
        "solution_design": {
            "action": "选择技术方案",
            "reason": "需要确定实现方案",
            "target_mode": "planning",
        },
        "development": {
            "action": "开始软件开发",
            "reason": "进入实现阶段",
            "target_mode": "development",
        },
        "testing": {
            "action": "运行测试验证",
            "reason": "验证产品是否满足要求",
            "target_mode": "testing",
        },
        "iteration": {
            "action": "根据反馈迭代",
            "reason": "持续改进产品",
            "target_mode": "learning",
        },
    }
    return mapping.get(project.current_stage)


def create_app(config: KyrozenConfig | None = None, model: ModelInterface | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _agent_factory, _config, _db, _project_manager, _context_builder, _learning_repository
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

        _db = create_database(_config)
        _project_manager = ProjectManager(_db)
        _context_builder = ProjectContextBuilder(_project_manager, InMemoryMemory())
        os.makedirs(_config.workspace_root, exist_ok=True)
        _learning_repository = LearningRepository(_db)

        _agent_factory = AgentFactory(
            config=_config,
            model=active_model,
            db=_db,
            project_manager=_project_manager,
            learning_repository=_learning_repository,
            logger=logger,
        )
        logger.agent("Kyrozen Core API started")
        yield
        logger.agent("Kyrozen Core API shutting down")

    app = FastAPI(title="Kyrozen Core API", version="0.2.0", lifespan=lifespan)

    resolved_config = config or get_config()
    allow_origins = resolved_config.cors_origins or []
    if not allow_origins:
        logger = get_logger(resolved_config.log_level)
        logger.warning(
            "CORS origins not configured (KYROZEN_CORS_ORIGINS). "
            "API will reject cross-origin requests."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger = get_logger(_config.log_level if _config else "info")
        logger.error(f"Unhandled exception at {request.method} {request.url.path}: {exc}")

        payload = None
        if (
            request.method in ("POST", "PUT", "PATCH")
            and request.url.path not in ("/api/chat", "/api/auth/me", "/api/auth/signin", "/api/auth/signup")
        ):
            try:
                body = await request.body()
                if body and len(body) <= 10 * 1024:
                    try:
                        payload = json.loads(body)
                    except Exception:
                        payload = {"raw": body.decode("utf-8", errors="replace")}
            except Exception:
                pass

        user_id = ""
        try:
            credentials = await security(request)
            if credentials:
                current_user = await get_current_user(request, credentials)
                user_id = current_user.user_id
        except Exception:
            pass

        project_id = request.path_params.get("project_id") or ""
        if not project_id and isinstance(payload, dict):
            project_id = payload.get("project_id") or ""

        if _db is not None:
            try:
                _db.save_error({
                    "user_id": user_id,
                    "project_id": project_id,
                    "endpoint": request.url.path,
                    "method": request.method,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "stack": traceback.format_exc(),
                    "payload": payload,
                })
            except Exception:
                logger.error("Failed to persist error log", exc_info=True)

        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Kyrozen Core</h1><p>Web UI not found.</p>")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    @app.get("/api/auth/me")
    async def api_auth_me(current_user: CurrentUser = Depends(get_current_user)):
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
        }

    def _auth_user_payload(user, fallback_email: str = "") -> dict[str, Any]:
        metadata = getattr(user, "user_metadata", None) or {}
        created_at = getattr(user, "created_at", None)
        return {
            "user_id": getattr(user, "id", ""),
            "email": getattr(user, "email", fallback_email),
            "name": metadata.get("name") if metadata else None,
            "role": metadata.get("role", "user") if metadata else "user",
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/api/auth/signup")
    async def api_auth_signup(request: SignupRequest):
        config = get_config()
        if not config.supabase_url or not config.supabase_service_role_key:
            raise HTTPException(status_code=500, detail="Supabase auth is not configured on the server")
        try:
            admin_client = create_client(config.supabase_url, config.supabase_service_role_key)
            name = request.name or request.email.split("@")[0]
            new_user = admin_client.auth.admin.create_user(
                {
                    "email": request.email,
                    "password": request.password,
                    "user_metadata": {"name": name},
                    "email_confirm": True,
                }
            )
            anon_client = create_client(config.supabase_url, config.supabase_anon_key)
            session = anon_client.auth.sign_in_with_password(
                {"email": request.email, "password": request.password}
            )
            return {
                "user": _auth_user_payload(new_user.user if hasattr(new_user, "user") else new_user, request.email),
                "access_token": session.session.access_token,
                "refresh_token": session.session.refresh_token,
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Registration failed: {exc}") from exc

    @app.post("/api/auth/signin")
    async def api_auth_signin(request: SigninRequest):
        config = get_config()
        if not config.supabase_url or not config.supabase_anon_key:
            raise HTTPException(status_code=500, detail="Supabase auth is not configured on the server")
        try:
            anon_client = create_client(config.supabase_url, config.supabase_anon_key)
            session = anon_client.auth.sign_in_with_password(
                {"email": request.email, "password": request.password}
            )
            return {
                "user": _auth_user_payload(session.user, request.email),
                "access_token": session.session.access_token,
                "refresh_token": session.session.refresh_token,
            }
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid credentials: {exc}") from exc

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    async def _stream_task_progress(agent, task, user_input: str, confirmed: bool):
        """Yield SSE events while an agent task runs in a background thread."""
        run_future = asyncio.create_task(asyncio.to_thread(agent.run_task, task, user_input, confirmed))
        last_status = None
        last_step_count = 0
        try:
            while True:
                await asyncio.sleep(1.0)
                current = agent.task_manager.get(task.id)
                if current is None:
                    yield f"data: {json.dumps({'error': 'Task disappeared'}, ensure_ascii=False)}\n\n"
                    break
                status = current.status
                step_count = len(current.steps)
                if status != last_status or step_count != last_step_count:
                    last_status = status
                    last_step_count = step_count
                    payload: dict[str, Any] = {
                        "task_id": task.id,
                        "status": status,
                        "steps": [s.to_dict() for s in current.steps],
                    }
                    if status == "completed":
                        payload["result"] = current.result
                    elif status == "failed":
                        payload["errors"] = current.errors
                    elif status == "waiting_confirmation":
                        step = next((s for s in reversed(current.steps) if s.status == "waiting_confirmation"), None)
                        if step and step.metadata:
                            payload["confirmation"] = step.metadata
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if status in ("completed", "failed", "cancelled", "waiting_confirmation"):
                    break
        finally:
            if not run_future.done():
                run_future.cancel()
                try:
                    await run_future
                except asyncio.CancelledError:
                    pass

    @app.post("/api/chat")
    async def api_chat(
        request: ChatRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        if request.mode == "discovery":
            agent = _get_discovery_agent()
        elif request.mode == "market_research":
            agent = _get_research_agent()
        elif request.mode == "planning":
            agent = _get_planning_agent()
        elif request.mode == "development":
            agent = _get_development_agent()
        elif request.mode == "hardware":
            agent = _get_hardware_agent()
        elif request.mode == "testing":
            agent = _get_testing_agent()
        elif request.mode == "learning":
            agent = _get_learning_agent()
        else:
            agent = _get_agent()
        if agent.model is None:
            raise HTTPException(503, "Model provider not configured. Set DEEPSEEK_API_KEY or KYROZEN_API_KEY.")

        user_input = request.message
        pm = _get_project_manager()
        user_message: dict[str, Any] | None = None
        if request.project_id:
            project = _get_owned_project(request.project_id, current_user)
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
            elif request.mode == "hardware":
                context = builder.build_hardware_context(project)
            elif request.mode == "testing":
                context = builder.build_testing_context(project)
            elif request.mode == "learning":
                context = builder.build_learning_context(project)
            else:
                context = builder.build(project)
            user_input = f"{context}\n{request.message}"
            # Ensure the agent uses the project's memory for this task
            if request.mode == "learning":
                agent.memory = _learning_repository
            else:
                agent.memory = _project_memory(request.project_id)

            user_message = {
                "id": str(uuid.uuid4()),
                "user_id": current_user.user_id,
                "project_id": request.project_id,
                "role": "user",
                "content": request.message,
                "metadata": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            pm.save_chat_message(user_message)
        else:
            # Use a global in-memory fallback if no project
            from kyrozen.memory import InMemoryMemory
            if not isinstance(agent.memory, InMemoryMemory):
                agent.memory = InMemoryMemory()

        def _assistant_content(task: Any) -> str:
            if not task.result:
                return "(no response)"
            if isinstance(task.result, dict):
                return task.result.get("answer") or str(task.result)
            return str(task.result)

        try:
            if request.stream:
                task = agent.task_manager.create(
                    title=user_input[:60],
                    description=user_input,
                    project_id=request.project_id,
                )
                return StreamingResponse(
                    _stream_task_progress(agent, task, user_input, request.confirmed),
                    media_type="text/event-stream",
                )
            task = agent.run(user_input, confirmed=request.confirmed, project_id=request.project_id)
            if request.project_id and user_message is not None:
                pm.save_chat_message(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": current_user.user_id,
                        "project_id": request.project_id,
                        "role": "assistant",
                        "content": _assistant_content(task),
                        "metadata": {},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            return {"task_id": task.id, "status": task.status, "project_id": request.project_id, "mode": request.mode}
        except Exception as e:
            if request.project_id and user_message is not None:
                pm.save_chat_message(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": current_user.user_id,
                        "project_id": request.project_id,
                        "role": "assistant",
                        "content": f"Error: {e}",
                        "metadata": {},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            raise HTTPException(500, f"Agent error: {e}") from e

    @app.get("/api/tasks/{task_id}")
    async def api_get_task(
        task_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        agent = _get_agent()
        task = agent.task_manager.get(task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        if task.project_id:
            _get_owned_project(task.project_id, current_user)
        return task.to_dict()

    @app.post("/api/tasks/{task_id}/confirm")
    async def api_confirm_task(
        task_id: str,
        request: ConfirmRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        agent = _get_agent()
        task = agent.task_manager.get(task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        if task.project_id:
            _get_owned_project(task.project_id, current_user)
        if task.status != "waiting_confirmation":
            raise HTTPException(400, f"Task is not waiting for confirmation (status={task.status})")
        if not request.confirmed:
            task.fail("User declined the high-risk action")
            agent.task_manager.update(task)
            return task.to_dict()

        user_input = task.description
        if task.project_id:
            project = _get_owned_project(task.project_id, current_user)
            builder = _get_context_builder()
            builder.memory = _project_memory(task.project_id)
            user_input = f"{builder.build(project)}\n{task.description}"
            agent.memory = _project_memory(task.project_id)

        task.update_status("running")
        agent.task_manager.update(task)
        task = agent.run(user_input, confirmed=True, project_id=task.project_id)
        return task.to_dict()

    @app.get("/api/tasks")
    async def api_list_tasks(
        project_id: str | None = None,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        agent = _get_agent()
        if project_id:
            _get_owned_project(project_id, current_user)
        return [task.to_dict() for task in agent.task_manager.list_tasks(project_id=project_id)]

    @app.get("/api/tools")
    async def api_list_tools():
        agent = _get_agent()
        return {"tools": agent.tools.list_schemas()}

    @app.post("/api/tools/execute")
    async def api_execute_tool(
        request: ToolExecuteRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        agent = _get_agent()
        decision = agent.permission.check(request.tool, request.action, request.parameters)
        if not decision.allowed:
            raise HTTPException(403, decision.reason)
        result = agent.tools.execute(request.tool, request.action, request.parameters)
        return result.to_dict()

    @app.get("/api/health")
    async def api_health():
        factory = _agent_factory
        model_ready = factory is not None and factory.model is not None
        return {
            "status": "ok" if model_ready else "degraded",
            "provider": _config.provider if _config else None,
            "model": _config.model_simple if _config else None,
            "permission_mode": _config.permission_mode if _config else None,
        }

    @app.get("/api/config")
    async def api_config(current_user: CurrentUser = Depends(get_current_user)):
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
            "provider_costs": {k: list(v) for k, v in _config.provider_costs.items()},
        }

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    @app.post("/api/projects")
    async def api_create_project(
        request: CreateProjectRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        project = pm.create(
            name=request.name,
            description=request.description,
            goal=request.goal,
            initial_idea=request.initial_idea,
            user_id=current_user.user_id,
        )
        # Ensure project directory and memory file exist
        if _config is not None:
            os.makedirs(_config.project_dir(project.id), exist_ok=True)
            _project_memory(project.id)
        return project.to_dict()

    @app.get("/api/projects")
    async def api_list_projects(current_user: CurrentUser = Depends(get_current_user)):
        pm = _get_project_manager()
        return [p.to_dict() for p in pm.list(user_id=current_user.user_id)]

    @app.get("/api/projects/{project_id}")
    async def api_get_project(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        project = _get_owned_project(project_id, current_user)
        data = project.to_dict()
        data["recent_tasks"] = [t.to_dict() for t in pm.list_tasks(project_id)[:5]]
        data["recent_decisions"] = [d.to_dict() for d in pm.list_decisions(project_id)[:5]]
        data["recent_artifacts"] = [a.to_dict() for a in pm.list_artifacts(project_id)[:5]]
        return data

    @app.put("/api/projects/{project_id}")
    async def api_update_project(
        project_id: str,
        request: UpdateProjectRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        project = pm.update(project_id, **updates)
        if project is None:
            raise HTTPException(404, "Project not found")
        return project.to_dict()

    @app.post("/api/projects/{project_id}/archive")
    async def api_archive_project(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        project = pm.archive(project_id)
        if project is None:
            raise HTTPException(404, "Project not found")
        return project.to_dict()

    @app.post("/api/projects/{project_id}/restore")
    async def api_restore_project(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        project = pm.restore(project_id)
        if project is None:
            raise HTTPException(400, "Project is not archived or does not exist")
        return project.to_dict()

    @app.delete("/api/projects/{project_id}")
    async def api_delete_project(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        deleted = pm.delete(project_id)
        if not deleted:
            raise HTTPException(404, "Project not found")
        # Clean up project workspace files after successful database deletion
        if _config is not None:
            project_dir = Path(_config.project_dir(project_id))
            if project_dir.exists():
                try:
                    shutil.rmtree(project_dir)
                except Exception as exc:
                    logger = get_logger(_config.log_level)
                    logger.warning(f"Failed to remove project directory {project_dir}: {exc}")
        return {"status": "deleted", "project_id": project_id}

    @app.get("/api/projects/{project_id}/state")
    async def api_project_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        next_action = _recommend_next_action(project)
        return {
            "project_id": project_id,
            "stage": project.current_stage,
            "progress": project.progress,
            "blocked_reason": project.blocked_reason or None,
            "next_action": next_action,
        }

    @app.get("/api/projects/{project_id}/chat")
    async def api_get_project_chat(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        pm = _get_project_manager()
        return pm.list_chat_messages(
            project_id=project_id,
            user_id=current_user.user_id,
        )

    @app.post("/api/projects/{project_id}/advance")
    async def api_advance_project(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        project = _get_owned_project(project_id, current_user)
        stages = list(PROJECT_STAGES)
        try:
            current_index = stages.index(project.current_stage)
        except ValueError:
            current_index = -1
        max_index = len(stages) - 1
        if current_index < max_index:
            next_index = current_index + 1
            new_stage = stages[next_index]
            original_stage = project.current_stage
            project.current_stage = new_stage
            next_action = _recommend_next_action(project)
            project.current_stage = original_stage
            next_steps = next_action["action"] if next_action else ""
            updated = pm.update(
                project_id,
                current_stage=new_stage,
                progress=next_index * 100 // max_index,
                next_steps=next_steps,
            )
        else:
            next_action = _recommend_next_action(project)
            updated = pm.update(
                project_id,
                status="completed",
                progress=100,
                next_steps=next_action["action"] if next_action else "",
            )
        if updated is None:
            raise HTTPException(404, "Project not found")
        return updated.to_dict()

    @app.get("/api/projects/{project_id}/tasks")
    async def api_project_tasks(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        return [t.to_dict() for t in pm.list_tasks(project_id)]

    @app.get("/api/projects/{project_id}/decisions")
    async def api_project_decisions(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        return [d.to_dict() for d in pm.list_decisions(project_id)]

    @app.post("/api/projects/{project_id}/decisions")
    async def api_create_decision(
        project_id: str,
        request: CreateDecisionRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
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
    async def api_project_artifacts(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        return [a.to_dict() for a in pm.list_artifacts(project_id)]

    @app.post("/api/projects/{project_id}/artifacts")
    async def api_create_artifact(
        project_id: str,
        request: CreateArtifactRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
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
    async def api_get_artifact(
        project_id: str,
        artifact_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        artifact = pm.get_artifact(project_id, artifact_id)
        if artifact is None:
            raise HTTPException(404, "Artifact not found")
        return artifact.to_dict()

    # ------------------------------------------------------------------
    # Feedback, Analytics & Error Monitoring
    # ------------------------------------------------------------------
    @app.post("/api/feedback")
    async def api_create_feedback(
        request: CreateFeedbackRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        if _db is None:
            raise HTTPException(503, "Database not initialized")
        if request.project_id:
            _get_owned_project(request.project_id, current_user)
        feedback_id = str(uuid.uuid4())
        now = _utc_now_iso()
        feedback = {
            "id": feedback_id,
            "user_id": current_user.user_id,
            "project_id": request.project_id,
            "type": request.type,
            "description": request.description,
            "priority": request.priority,
            "status": "open",
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }
        _db.save_feedback(feedback)
        return feedback

    @app.get("/api/feedback")
    async def api_list_feedback(
        current_user: CurrentUser = Depends(get_current_user),
        admin: CurrentUser = Depends(require_admin),
    ):
        if _db is None:
            raise HTTPException(503, "Database not initialized")
        if admin.is_admin():
            return _db.list_feedback()
        return _db.list_feedback(user_id=current_user.user_id)

    @app.post("/api/events")
    async def api_create_event(
        request: CreateEventRequest,
        current_user: CurrentUser | None = Depends(get_current_user_optional),
    ):
        if _db is None:
            raise HTTPException(503, "Database not initialized")
        user_id = current_user.user_id if current_user else None
        if request.project_id and current_user:
            _get_owned_project(request.project_id, current_user)
        event = {
            "user_id": user_id,
            "project_id": request.project_id,
            "event_type": request.event_type,
            "payload": request.payload,
            "session_id": request.session_id,
            "created_at": _utc_now_iso(),
        }
        _db.save_event(event)
        return {"status": "ok"}

    @app.get("/api/analytics/summary", response_model=AnalyticsSummaryResponse)
    async def api_analytics_summary(
        admin: CurrentUser = Depends(require_admin),
    ):
        if _db is None:
            raise HTTPException(503, "Database not initialized")
        events = _db.list_events(limit=10000)
        feedback = _db.list_feedback()
        events_by_type: dict[str, int] = {}
        unique_users: set[str] = set()
        for event in events:
            event_type = event.get("event_type", "unknown")
            events_by_type[event_type] = events_by_type.get(event_type, 0) + 1
            user_id = event.get("user_id")
            if user_id:
                unique_users.add(user_id)
        feedback_by_type: dict[str, int] = {}
        for item in feedback:
            feedback_type = item.get("type", "unknown")
            feedback_by_type[feedback_type] = feedback_by_type.get(feedback_type, 0) + 1
            user_id = item.get("user_id")
            if user_id:
                unique_users.add(user_id)
        return AnalyticsSummaryResponse(
            total_events=len(events),
            events_by_type=events_by_type,
            unique_users=len(unique_users),
            total_feedback=len(feedback),
            feedback_by_type=feedback_by_type,
        )

    # ------------------------------------------------------------------
    # Problem Discovery
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/problem-discovery/state")
    async def api_discovery_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
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
    async def api_market_research_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
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
    async def api_planning_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
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
    async def api_development_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
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

    # ------------------------------------------------------------------
    # Hardware Development
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/hardware/state")
    async def api_hardware_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        from kyrozen.hardware.models import (
            BOM,
            FirmwareProject,
            HardwareArchitecture,
            WiringDesign,
        )

        latest_arch = pm.get_latest_artifact(
            project_id, "hardware_architecture", title="Hardware Architecture"
        )
        arch = HardwareArchitecture()
        if latest_arch is not None:
            import json
            try:
                arch = HardwareArchitecture.from_dict(json.loads(latest_arch.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_bom = pm.get_latest_artifact(project_id, "bom", title="Bill of Materials")
        bom = BOM()
        if latest_bom is not None:
            import json
            try:
                bom = BOM.from_dict(json.loads(latest_bom.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_wiring = pm.get_latest_artifact(
            project_id, "wiring_design", title="Wiring Design"
        )
        wiring = WiringDesign()
        if latest_wiring is not None:
            import json
            try:
                wiring = WiringDesign.from_dict(json.loads(latest_wiring.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_firmware = pm.get_latest_artifact(
            project_id, "firmware_project", title="Firmware Project"
        )
        firmware = FirmwareProject()
        if latest_firmware is not None:
            import json
            try:
                firmware = FirmwareProject.from_dict(json.loads(latest_firmware.content))
            except (json.JSONDecodeError, ValueError):
                pass

        assembly_steps = []
        debug_records = []
        for artifact in pm.list_artifacts(project_id):
            if artifact.type == "assembly_step":
                try:
                    from kyrozen.hardware.models import AssemblyStep
                    assembly_steps.append(AssemblyStep.from_dict(json.loads(artifact.content)))
                except (json.JSONDecodeError, ValueError):
                    pass
            elif artifact.type == "hardware_debug_record":
                try:
                    from kyrozen.hardware.models import HardwareDebugRecord
                    debug_records.append(HardwareDebugRecord.from_dict(json.loads(artifact.content)))
                except (json.JSONDecodeError, ValueError):
                    pass

        decisions = [
            d for d in pm.list_decisions(project_id)
            if d.decision.startswith("Hardware decision:")
        ]

        # Summarize git commits if hardware project exists
        import subprocess
        from pathlib import Path

        git_log: list[str] = []
        if _config is not None:
            hardware_dir = Path(_config.project_dir(project_id)) / "hardware"
            if (hardware_dir / ".git").exists():
                try:
                    result = subprocess.run(
                        ["git", "-C", str(hardware_dir), "log", "--oneline", "-10"],
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
            "architecture": arch.to_dict(),
            "bom": bom.to_dict(),
            "wiring": wiring.to_dict(),
            "firmware": firmware.to_dict(),
            "assembly_steps": [s.to_dict() for s in assembly_steps],
            "debug_records": [r.to_dict() for r in debug_records],
            "decisions": [d.to_dict() for d in decisions[-5:]],
            "git_log": git_log,
            "latest_arch_artifact_id": latest_arch.id if latest_arch else None,
            "latest_bom_artifact_id": latest_bom.id if latest_bom else None,
            "latest_wiring_artifact_id": latest_wiring.id if latest_wiring else None,
            "latest_firmware_artifact_id": latest_firmware.id if latest_firmware else None,
        }

    # ------------------------------------------------------------------
    # Testing & Validation
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/testing/state")
    async def api_testing_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)
        from kyrozen.testing.models import TestPlan, ValidationReport

        latest_test_plan = pm.get_latest_artifact(project_id, "test_plan", title="Test Plan")
        test_plan = TestPlan()
        if latest_test_plan is not None:
            import json
            try:
                test_plan = TestPlan.from_dict(json.loads(latest_test_plan.content))
            except (json.JSONDecodeError, ValueError):
                pass

        test_results = []
        user_feedback = []
        for artifact in pm.list_artifacts(project_id):
            if artifact.type == "test_result":
                try:
                    from kyrozen.testing.models import TestResult
                    test_results.append(TestResult.from_dict(json.loads(artifact.content)))
                except (json.JSONDecodeError, ValueError):
                    pass
            elif artifact.type == "user_feedback":
                try:
                    from kyrozen.testing.models import UserFeedback
                    user_feedback.append(UserFeedback.from_dict(json.loads(artifact.content)))
                except (json.JSONDecodeError, ValueError):
                    pass

        latest_validation = pm.get_latest_artifact(
            project_id, "validation_report", title="Validation Report"
        )
        validation_report = ValidationReport()
        if latest_validation is not None:
            import json
            try:
                validation_report = ValidationReport.from_dict(json.loads(latest_validation.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_iteration = pm.get_latest_artifact(
            project_id, "iteration_plan", title="Iteration Plan"
        )
        iteration_plan = {"items": [], "overall_recommendation": ""}
        if latest_iteration is not None:
            import json
            try:
                iteration_plan = json.loads(latest_iteration.content)
            except (json.JSONDecodeError, ValueError):
                pass

        decisions = [
            d for d in pm.list_decisions(project_id)
            if d.decision.startswith("Testing decision:") or d.decision.startswith("Validation decision:")
        ]

        return {
            "project_id": project_id,
            "test_plan": test_plan.to_dict(),
            "test_results": [r.to_dict() for r in test_results],
            "user_feedback": [fb.to_dict() for fb in user_feedback],
            "validation_report": validation_report.to_dict(),
            "iteration_plan": iteration_plan,
            "decisions": [d.to_dict() for d in decisions[-5:]],
            "latest_test_plan_artifact_id": latest_test_plan.id if latest_test_plan else None,
            "latest_validation_artifact_id": latest_validation.id if latest_validation else None,
            "latest_iteration_artifact_id": latest_iteration.id if latest_iteration else None,
        }

    # ------------------------------------------------------------------
    # Learning & Proactive Improvement
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/learning/state")
    async def api_learning_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)

        repo = _get_learning_repository()
        learning_records = []
        failure_knowledge = []
        success_knowledge = []
        if repo is not None:
            for record in repo.list_records(source_project_id=project_id, limit=100, user_id=current_user.user_id):
                if record.memory_type == "validated_failure":
                    failure_knowledge.append(record.to_dict())
                elif record.memory_type == "validated_success":
                    success_knowledge.append(record.to_dict())
                else:
                    learning_records.append(record.to_dict())
            failure_knowledge.extend(
                f.to_dict() for f in repo.list_failures(source_project_id=project_id, limit=100, user_id=current_user.user_id)
            )
            success_knowledge.extend(
                s.to_dict() for s in repo.list_successes(source_project_id=project_id, limit=100, user_id=current_user.user_id)
            )

        return {
            "project_id": project_id,
            "learning_records": learning_records,
            "failure_knowledge": failure_knowledge,
            "success_knowledge": success_knowledge,
        }

    @app.get("/api/projects/{project_id}/improvement/state")
    async def api_improvement_state(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        _get_owned_project(project_id, current_user)

        repo = _learning_repository
        suggestions = []
        if repo is not None:
            suggestions = [
                s.to_dict()
                for s in repo.list_suggestions(source_project_id=project_id, limit=100, user_id=current_user.user_id)
            ]

        return {
            "project_id": project_id,
            "suggestions": suggestions,
        }

    # ------------------------------------------------------------------
    # Learning CRUD
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/learning/records")
    async def api_list_learning_records(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        return [r.to_dict() for r in repo.list_records(source_project_id=project_id, user_id=current_user.user_id)]

    @app.post("/api/projects/{project_id}/learning/records")
    async def api_create_learning_record(
        project_id: str,
        request: CreateLearningRecordRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        from kyrozen.learning.models import LearningRecord
        record = LearningRecord(
            memory=request.memory,
            memory_type=request.memory_type,
            source=request.source,
            source_project_id=project_id,
            confidence=request.confidence,
            verification_status=request.verification_status,
            scope=request.scope,
            tags=request.tags,
        )
        repo.save_record(record, user_id=current_user.user_id)
        return record.to_dict()

    @app.get("/api/projects/{project_id}/learning/records/{record_id}")
    async def api_get_learning_record(
        project_id: str,
        record_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        record = repo.get_record(record_id, user_id=current_user.user_id)
        if record is None or record.source_project_id != project_id:
            raise HTTPException(404, "Record not found")
        return record.to_dict()

    @app.delete("/api/projects/{project_id}/learning/records/{record_id}")
    async def api_delete_learning_record(
        project_id: str,
        record_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        record = repo.get_record(record_id, user_id=current_user.user_id)
        if record is None or record.source_project_id != project_id:
            raise HTTPException(404, "Record not found")
        repo.delete_record(record_id, user_id=current_user.user_id)
        return {"status": "deleted"}

    @app.get("/api/projects/{project_id}/learning/failures")
    async def api_list_failure_knowledge(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        return [f.to_dict() for f in repo.list_failures(source_project_id=project_id, user_id=current_user.user_id)]

    @app.post("/api/projects/{project_id}/learning/failures")
    async def api_create_failure_knowledge(
        project_id: str,
        request: CreateFailureKnowledgeRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        from kyrozen.learning.models import FailureKnowledge
        failure = FailureKnowledge(
            problem=request.problem,
            cause=request.cause,
            solution=request.solution,
            affected_scope=request.affected_scope,
            verification=request.verification,
            source_project_id=project_id,
            confidence=request.confidence,
            verification_status=request.verification_status,
        )
        repo.save_failure(failure, user_id=current_user.user_id)
        return failure.to_dict()

    @app.get("/api/projects/{project_id}/learning/failures/{failure_id}")
    async def api_get_failure_knowledge(
        project_id: str,
        failure_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        failure = repo.get_failure(failure_id, user_id=current_user.user_id)
        if failure is None or failure.source_project_id != project_id:
            raise HTTPException(404, "Failure knowledge not found")
        return failure.to_dict()

    @app.delete("/api/projects/{project_id}/learning/failures/{failure_id}")
    async def api_delete_failure_knowledge(
        project_id: str,
        failure_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        failure = repo.get_failure(failure_id, user_id=current_user.user_id)
        if failure is None or failure.source_project_id != project_id:
            raise HTTPException(404, "Failure knowledge not found")
        repo.delete_failure(failure_id, user_id=current_user.user_id)
        return {"status": "deleted"}

    @app.get("/api/projects/{project_id}/learning/successes")
    async def api_list_success_knowledge(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        return [s.to_dict() for s in repo.list_successes(source_project_id=project_id, user_id=current_user.user_id)]

    @app.post("/api/projects/{project_id}/learning/successes")
    async def api_create_success_knowledge(
        project_id: str,
        request: CreateSuccessKnowledgeRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        from kyrozen.learning.models import SuccessKnowledge
        success = SuccessKnowledge(
            goal=request.goal,
            solution=request.solution,
            conditions=request.conditions,
            result=request.result,
            source_project_id=project_id,
            confidence=request.confidence,
            verification_status=request.verification_status,
        )
        repo.save_success(success, user_id=current_user.user_id)
        return success.to_dict()

    @app.get("/api/projects/{project_id}/learning/successes/{success_id}")
    async def api_get_success_knowledge(
        project_id: str,
        success_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        success = repo.get_success(success_id, user_id=current_user.user_id)
        if success is None or success.source_project_id != project_id:
            raise HTTPException(404, "Success knowledge not found")
        return success.to_dict()

    @app.delete("/api/projects/{project_id}/learning/successes/{success_id}")
    async def api_delete_success_knowledge(
        project_id: str,
        success_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        success = repo.get_success(success_id, user_id=current_user.user_id)
        if success is None or success.source_project_id != project_id:
            raise HTTPException(404, "Success knowledge not found")
        repo.delete_success(success_id, user_id=current_user.user_id)
        return {"status": "deleted"}

    @app.get("/api/projects/{project_id}/learning/suggestions")
    async def api_list_suggestions(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        return [s.to_dict() for s in repo.list_suggestions(source_project_id=project_id, user_id=current_user.user_id)]

    @app.post("/api/projects/{project_id}/learning/suggestions")
    async def api_create_suggestion(
        project_id: str,
        request: CreateSuggestionRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        from kyrozen.learning.models import Suggestion
        suggestion = Suggestion(
            suggestion=request.suggestion,
            reason=request.reason,
            source_project_id=project_id,
            evidence=request.evidence,
            impact=request.impact,
            priority=request.priority,
            status=request.status,
            category=request.category,
            related_learning_ids=request.related_learning_ids,
        )
        repo.save_suggestion(suggestion, user_id=current_user.user_id)
        return suggestion.to_dict()

    @app.get("/api/projects/{project_id}/learning/suggestions/{suggestion_id}")
    async def api_get_suggestion(
        project_id: str,
        suggestion_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        suggestion = repo.get_suggestion(suggestion_id, user_id=current_user.user_id)
        if suggestion is None or suggestion.source_project_id != project_id:
            raise HTTPException(404, "Suggestion not found")
        return suggestion.to_dict()

    @app.patch("/api/projects/{project_id}/learning/suggestions/{suggestion_id}/status")
    async def api_update_suggestion_status(
        project_id: str,
        suggestion_id: str,
        request: UpdateSuggestionStatusRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        suggestion = repo.get_suggestion(suggestion_id, user_id=current_user.user_id)
        if suggestion is None or suggestion.source_project_id != project_id:
            raise HTTPException(404, "Suggestion not found")
        repo.update_suggestion_status(suggestion_id, request.status, user_id=current_user.user_id)
        return {"status": "updated"}

    @app.delete("/api/projects/{project_id}/learning/suggestions/{suggestion_id}")
    async def api_delete_suggestion(
        project_id: str,
        suggestion_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        repo = _get_learning_repository()
        suggestion = repo.get_suggestion(suggestion_id, user_id=current_user.user_id)
        if suggestion is None or suggestion.source_project_id != project_id:
            raise HTTPException(404, "Suggestion not found")
        repo.delete_suggestion(suggestion_id, user_id=current_user.user_id)
        return {"status": "deleted"}

    return app


app = create_app()
