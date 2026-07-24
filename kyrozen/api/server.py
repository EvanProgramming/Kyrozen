"""FastAPI web server and REST API for Kyrozen Core testing."""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import asynccontextmanager
import traceback
import uuid
from pathlib import Path
from typing import Any

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from supabase import create_client

from kyrozen.auth.context import current_user_ctx
from kyrozen.auth.dependencies import (
    CurrentUser,
    _decode_supabase_token,
    get_current_user,
    get_current_user_optional,
    require_admin,
)
from kyrozen.config import KyrozenConfig, get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import TaskManager
from kyrozen.desktop import DesktopClientManager, DesktopTokenManager, QuotaManager
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
_desktop_manager: DesktopClientManager | None = None
_quota_manager: QuotaManager | None = None


_KYROZEN_QUESTION_RE = re.compile(r"```kyrozen-question\s*([\s\S]*?)\s*```")


def _extract_question_text(content: str) -> str:
    """Extract the question field from a kyrozen-question JSON block if present.

    Falls back to returning the text with the block removed.
    """
    match = _KYROZEN_QUESTION_RE.search(content)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            question = data.get("question", "").strip()
            if question:
                return question
        except json.JSONDecodeError:
            pass
    # Fallback: remove the block and clean surrounding text.
    return _KYROZEN_QUESTION_RE.sub("", content).strip()


def _strip_question_block(content: str) -> str:
    """Remove the kyrozen-question JSON block from an assistant message."""
    return _KYROZEN_QUESTION_RE.sub("", content).strip()


# Common option-value mappings used by the frontend. These normalisations make
# sure terse option values (e.g. "no_tracking") are interpreted as real brief
# fields so the agent does not ask about the same dimension again.
_DISCOVERY_OPTION_MAPPINGS: dict[str, dict[str, str]] = {
    "target_user": {
        "myself": "myself",
        "self": "myself",
        "family": "family member",
        "friend": "a friend",
        "small_business": "small business owner",
        "business": "business owner",
        "team": "a team",
        "students": "students",
        "elders": "elderly people",
    },
    "current_solution": {
        "no_tracking": "not tracking income/expenses at all",
        "not_tracking": "not tracking income/expenses at all",
        "notebook": "notebook / paper",
        "excel": "Excel spreadsheet",
        "spreadsheet": "spreadsheet",
        "memo": "phone memo / notes app",
        "calculator": "calculator",
        "app": "existing mobile app",
        "none": "no existing solution",
    },
    "deep_need": {
        "curiosity": "understand personal spending habits",
        "save_money": "save money for a goal",
        "control_spending": "control spending in specific categories",
        "budget": "stick to a budget",
        "plan": "plan future spending",
    },
}


def _apply_discovery_option_mappings(answer: str) -> dict[str, str]:
    """Return brief fields inferred from known option values."""
    normalized = answer.strip().lower()
    result: dict[str, str] = {}
    for field, mappings in _DISCOVERY_OPTION_MAPPINGS.items():
        for option_key, mapped_value in mappings.items():
            if normalized == option_key.lower():
                result[field] = mapped_value
                break
    return result


def _record_discovery_qa(
    project_id: str,
    user_id: str,
    answer: str,
    pm: ProjectManager,
) -> str | None:
    """Store the latest Q&A pair from chat history into project memory.

    This lets the discovery agent see what has already been asked and answered
    so it does not repeat questions. Returns the cleaned question text, or None
    for the very first user message (which has no preceding assistant question).
    """
    try:
        messages = pm.list_chat_messages(project_id=project_id, user_id=user_id, limit=20)
        if not messages:
            return None
        # messages are ordered oldest -> newest; find the assistant message
        # immediately before the most recent user message.
        last_user_index = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                last_user_index = i
                break
        if last_user_index is None or last_user_index == 0:
            return None
        previous = messages[last_user_index - 1]
        if previous["role"] != "assistant":
            return None
        question = _extract_question_text(previous["content"]) or "Follow-up question"
        memory = _project_memory(project_id)
        memory.save(
            category="discovery_qa",
            content=answer,
            question=question,
            user_id=user_id,
        )
        return question
    except Exception:
        # Memory saving must not break the chat flow.
        get_logger(__name__).warning("Failed to record discovery Q&A", exc_info=True)
        return None


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model response, tolerating markdown fences."""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


async def _auto_update_discovery_brief(
    project_id: str,
    question: str,
    answer: str,
    pm: ProjectManager,
    model: ModelInterface,
) -> None:
    """Infer Problem Brief fields from the latest Q&A and persist them.

    This is a deterministic fallback so the agent does not have to rely on the
    LLM calling save_problem_brief after every answer.
    """
    from kyrozen.discovery.brief import ProblemBrief

    try:
        latest = pm.get_latest_artifact(project_id, "problem_brief", title="Problem Brief")
        current_brief = ProblemBrief()
        if latest is not None:
            try:
                current_brief = ProblemBrief.from_dict(json.loads(latest.content))
            except Exception:
                pass

        # Start with deterministic mappings for known terse option values.
        extracted = _apply_discovery_option_mappings(answer)

        # Use the model to extract any additional structured fields.
        system = (
            "You extract structured Problem Brief fields from a user answer. "
            "Given the current brief, the assistant's last question, and the user's answer, "
            "return a JSON object with any fields you can infer. Use only these keys: "
            "target_user, scenario, surface_problem, current_solution, deep_need, frequency, impact. "
            "Map terse option values to meaningful descriptions, e.g. 'no_tracking' -> "
            "'not tracking income/expenses at all', 'myself' -> 'myself', 'curiosity' -> "
            "'understand personal spending habits'. "
            "If a field is unknown or unchanged, omit it. Return only JSON, no commentary."
        )
        prompt = (
            f"Current brief: {json.dumps(current_brief.to_dict(), ensure_ascii=False)}\n\n"
            f"Assistant question: {question}\n"
            f"User answer: {answer}\n\n"
            "Return updated fields as JSON."
        )
        response = await asyncio.to_thread(
            model.chat,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        model_extracted = _parse_json_response(response.content)
        if isinstance(model_extracted, dict):
            for key, value in model_extracted.items():
                if value not in (None, "", []) and key not in extracted:
                    extracted[key] = value

        extracted = {k: v for k, v in extracted.items() if v not in (None, "", [])}
        if not extracted:
            return

        new_brief = ProblemBrief.from_dict(extracted)
        merged = current_brief.merge(new_brief)
        content = json.dumps(merged.to_dict(), ensure_ascii=False, indent=2)
        pm.save_artifact(
            project_id=project_id,
            type="problem_brief",
            title="Problem Brief",
            content=content,
            change_reason="Auto-updated from discovery Q&A",
        )
    except Exception:
        get_logger(__name__).warning("Failed to auto-update discovery brief", exc_info=True)


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


class DesktopOpenTokenRequest(BaseModel):
    project_id: str | None = Field(None, description="Project ID to pre-select in the desktop client")


class DesktopVerifyTokenRequest(BaseModel):
    token: str | None = Field(None, description="Short-lived open token from /api/desktop/open-token")
    access_token: str | None = Field(None, description="Long-lived access token from /api/auth/signin")
    device_name: str = Field("Unknown Device", description="Desktop client device name")
    client_version: str = Field("", description="Desktop client version")
    platform: str = Field("", description="Desktop client platform")

    def model_post_init(self, __context: Any) -> None:
        if not self.token and not self.access_token:
            raise ValueError("Either token or access_token must be provided")


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


class CreateFileSummaryRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    event: str = Field(..., pattern="^(changed|created|deleted|renamed)$")
    summary: str = ""
    content_snippet: str = ""


class CreateWebCaptureRequest(BaseModel):
    url: str = Field(..., min_length=1)
    title: str = ""
    content: str = ""


class WebTestRequest(BaseModel):
    url: str = Field(..., min_length=1)
    title: str = ""
    expected_text: str = ""


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


def _get_desktop_manager() -> DesktopClientManager:
    if _desktop_manager is None:
        raise RuntimeError("Desktop manager not initialized")
    return _desktop_manager


def _get_quota_manager() -> QuotaManager:
    if _quota_manager is None:
        raise RuntimeError("Quota manager not initialized")
    return _quota_manager


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


def _requires_local_client(mode: str) -> bool:
    """Return True for modes that need the local desktop client."""
    return mode in {"development", "hardware"}


async def _route_task_to_desktop(task: Any, user_id: str) -> bool:
    """Try to dispatch a local-client task to an online desktop client.

    Returns True if the task was pushed to a client.
    """
    manager = _get_desktop_manager()
    client = manager.pick_client_for_task(user_id, task.project_id)
    if client is None:
        return False
    dispatched = await manager.send_to_client(
        client.client_id,
        {
            "type": "assign_task",
            "task_id": task.id,
            "project_id": task.project_id,
            "mode": task.mode,
            "message": task.description,
            "requires_confirmation": True,
        },
    )
    if dispatched:
        task.assigned_client_id = client.client_id
        if task.status == "pending":
            task.update_status("running")
        if _db is not None:
            try:
                _db.save_task(task)
            except Exception as exc:
                get_logger(__name__).warning("Failed to save routed task", exc_info=True)
    return dispatched


async def _handle_model_request(
    websocket: WebSocket,
    message: dict[str, Any],
    user_id: str,
    logger: Any,
) -> None:
    """Proxy a model request from a desktop client to the configured cloud model.

    Sends chunks back as model_stream_chunk messages. Enforces the per-user
    token quota before executing the request and records actual usage after.
    """
    request_id = message.get("request_id")
    messages = message.get("messages", [])
    stream = message.get("stream", True)

    quota = _get_quota_manager().check_quota(user_id)
    if not quota.allowed:
        await websocket.send_json({
            "type": "model_error",
            "request_id": request_id,
            "error": quota.reason,
        })
        return

    factory = _get_agent_factory()
    model = factory.model
    if model is None:
        await websocket.send_json({
            "type": "model_error",
            "request_id": request_id,
            "error": "Model provider not configured on the server.",
        })
        return

    def _estimate_tokens(text: str) -> int:
        """Rough token estimator for usage tracking when the provider does not report tokens."""
        return max(1, len(text) // 4)

    try:
        if not stream:
            response = await asyncio.to_thread(model.chat, messages)
            prompt_tokens = response.usage.prompt_tokens if response.usage else _estimate_tokens("".join(m.get("content", "") for m in messages))
            completion_tokens = response.usage.completion_tokens if response.usage else _estimate_tokens(response.content)
            _get_quota_manager().record_usage(user_id, prompt_tokens, completion_tokens)
            await websocket.send_json({
                "type": "model_stream_chunk",
                "request_id": request_id,
                "chunk": "",
                "finished": True,
                "full_content": response.content,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            })
            return

        full_content_parts: list[str] = []
        for chunk in await asyncio.to_thread(lambda: list(model.chat_stream(messages))):
            full_content_parts.append(chunk)
            await websocket.send_json({
                "type": "model_stream_chunk",
                "request_id": request_id,
                "chunk": chunk,
                "finished": False,
            })

        full_content = "".join(full_content_parts)
        prompt_tokens = _estimate_tokens("".join(m.get("content", "") for m in messages))
        completion_tokens = _estimate_tokens(full_content)
        _get_quota_manager().record_usage(user_id, prompt_tokens, completion_tokens)
        await websocket.send_json({
            "type": "model_stream_chunk",
            "request_id": request_id,
            "chunk": "",
            "finished": True,
            "full_content": full_content,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        })
    except Exception as exc:
        logger.warning(f"Model proxy error for request {request_id}: {exc}")
        await websocket.send_json({
            "type": "model_error",
            "request_id": request_id,
            "error": f"Model request failed: {exc}",
        })


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
        global _agent_factory, _config, _db, _project_manager, _context_builder, _learning_repository, _desktop_manager, _quota_manager
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
        _project_manager = ProjectManager(_db, workspace_root=_config.workspace_root)
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
        _desktop_manager = DesktopClientManager()
        _quota_manager = QuotaManager(default_limit=_config.desktop_quota_default_limit)
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
    # GitHub OAuth
    # ------------------------------------------------------------------
    _github_oauth_states: dict[str, dict[str, Any]] = {}

    class GitHubAuthorizeRequest(BaseModel):
        redirect_uri: str | None = None
        desktop: bool = False

    def _cleanup_github_oauth_states() -> None:
        now = datetime.now(timezone.utc).timestamp()
        expired = [k for k, v in _github_oauth_states.items() if v.get("expires_at", 0) < now]
        for k in expired:
            _github_oauth_states.pop(k, None)

    @app.get("/api/auth/github/authorize")
    async def api_github_authorize(
        request: Request,
        redirect_uri: str | None = None,
        desktop: bool = False,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        config = get_config()
        if not config.github_oauth_client_id or not config.github_oauth_client_secret:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on the server")

        _cleanup_github_oauth_states()
        state = uuid.uuid4().hex
        callback_uri = redirect_uri or config.github_oauth_redirect_uri or str(request.base_url).rstrip("/") + "/api/auth/github/callback"
        _github_oauth_states[state] = {
            "user_id": current_user.user_id,
            "desktop": desktop,
            "redirect_uri": callback_uri,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp(),
        }

        params = {
            "client_id": config.github_oauth_client_id,
            "redirect_uri": callback_uri,
            "state": state,
            "scope": "repo read:user",
        }
        authorize_url = "https://github.com/login/oauth/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
        return {"authorize_url": authorize_url}

    @app.get("/api/auth/github/callback")
    async def api_github_callback(
        code: str,
        state: str,
    ):
        _cleanup_github_oauth_states()
        state_data = _github_oauth_states.pop(state, None)
        if not state_data:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

        user_id = state_data.get("user_id")

        config = get_config()
        if not config.github_oauth_client_id or not config.github_oauth_client_secret:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on the server")

        try:
            import requests
        except ImportError as exc:
            raise HTTPException(status_code=500, detail=f"requests is not installed: {exc}") from exc

        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": config.github_oauth_client_id,
                "client_secret": config.github_oauth_client_secret,
                "code": code,
                "redirect_uri": state_data["redirect_uri"],
            },
            timeout=30,
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub token exchange failed")

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=502, detail=f"GitHub did not return an access token: {token_data}")

        # Persist the GitHub token in Supabase user metadata so it can be used
        # by the agent for repository operations.
        try:
            if config.supabase_url and config.supabase_service_role_key:
                admin_client = create_client(config.supabase_url, config.supabase_service_role_key)
                admin_client.auth.admin.update_user_by_id(
                    user_id,
                    {
                        "user_metadata": {
                            "github_access_token": access_token,
                            "github_token_scopes": token_data.get("scope", ""),
                        }
                    },
                )
        except Exception as exc:
            get_logger(__name__).warning("Failed to persist GitHub token to Supabase: %s", exc, exc_info=True)

        scope = token_data.get("scope", "")
        is_desktop = state_data.get("desktop", False)
        if is_desktop:
            return HTMLResponse(
                content=(
                    "<html><body style='font-family:system-ui,sans-serif;text-align:center;padding:48px;'>"
                    "<h1>GitHub 授权成功</h1>"
                    "<p>请回到 Kyrozen 桌面客户端继续操作。</p>"
                    "<script>setTimeout(() => window.close(), 3000);</script>"
                    "</body></html>"
                )
            )
        return {
            "success": True,
            "scope": scope,
            "desktop": is_desktop,
        }

    @app.get("/api/user/github-status")
    async def api_user_github_status(current_user: CurrentUser = Depends(get_current_user)):
        metadata = current_user.raw_claims.get("user_metadata", {}) or {}
        token = metadata.get("github_access_token")
        return {
            "connected": bool(token),
            "scope": metadata.get("github_token_scopes", ""),
        }

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
        context: str | None = None
        if request.project_id:
            project = _get_owned_project(request.project_id, current_user)

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

            # For discovery mode, capture the latest Q&A and update the Problem Brief
            # BEFORE building context so the agent sees the freshest state.
            if request.mode == "discovery":
                last_question = _record_discovery_qa(
                    request.project_id,
                    current_user.user_id,
                    request.message,
                    pm,
                )
                if last_question is None:
                    # First user message: still try to extract fields from it.
                    last_question = "Initial problem description"
                if agent.model is not None:
                    await _auto_update_discovery_brief(
                        request.project_id,
                        last_question,
                        request.message,
                        pm,
                        agent.model,
                    )

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
                    mode=request.mode,
                    requires_local_client=_requires_local_client(request.mode),
                )
                if _requires_local_client(request.mode):
                    routed = await _route_task_to_desktop(task, current_user.user_id)
                    if routed:
                        return {
                            "task_id": task.id,
                            "status": task.status,
                            "project_id": request.project_id,
                            "mode": request.mode,
                            "dispatched_to_desktop": True,
                        }
                return StreamingResponse(
                    _stream_task_progress(agent, task, user_input, request.confirmed),
                    media_type="text/event-stream",
                )

            task = agent.task_manager.create(
                title=user_input[:60],
                description=user_input,
                project_id=request.project_id,
                mode=request.mode,
                requires_local_client=_requires_local_client(request.mode),
            )
            if _requires_local_client(request.mode):
                routed = await _route_task_to_desktop(task, current_user.user_id)
                if routed:
                    content = (
                        "任务已推送到你的 Kyrozen 桌面客户端执行。"
                        "请在桌面客户端中查看进度。"
                    )
                    if request.project_id and user_message is not None:
                        pm.save_chat_message(
                            {
                                "id": str(uuid.uuid4()),
                                "user_id": current_user.user_id,
                                "project_id": request.project_id,
                                "role": "assistant",
                                "content": content,
                                "metadata": {"dispatched_to_desktop": True},
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    return {
                        "task_id": task.id,
                        "status": task.status,
                        "project_id": request.project_id,
                        "mode": request.mode,
                        "dispatched_to_desktop": True,
                    }

            agent.run_task(task, user_input, confirmed=request.confirmed)
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

    @app.post("/api/projects/{project_id}/file-summaries")
    async def api_create_file_summary(
        project_id: str,
        request: CreateFileSummaryRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        try:
            memory = _project_memory(project_id)
            record = memory.save(
                category="local_file_summary",
                content=request.summary or f"{request.event}: {request.file_path}",
                file_path=request.file_path,
                event=request.event,
                content_snippet=request.content_snippet,
            )
            return record.to_dict()
        except Exception as exc:
            raise HTTPException(500, f"Failed to save file summary: {exc}") from exc

    @app.post("/api/projects/{project_id}/web-captures")
    async def api_create_web_capture(
        project_id: str,
        request: CreateWebCaptureRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        try:
            memory = _project_memory(project_id)
            record = memory.save(
                category="web_capture",
                content=request.content or request.title or request.url,
                url=request.url,
                title=request.title,
            )
            return record.to_dict()
        except Exception as exc:
            raise HTTPException(500, f"Failed to save web capture: {exc}") from exc

    @app.post("/api/projects/{project_id}/web-test")
    async def api_web_test(
        project_id: str,
        request: WebTestRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        try:
            factory = _get_agent_factory()
            result = factory.tools.execute(
                "web_test",
                "test_local_app",
                {"url": request.url, "expected_text": request.expected_text},
            )
            # Also store a snapshot of the tested page in project memory.
            try:
                memory = _project_memory(project_id)
                memory.save(
                    category="web_capture",
                    content=request.title or request.url,
                    url=request.url,
                    title=request.title,
                )
            except Exception:
                get_logger(__name__).warning("Failed to save web-test snapshot", exc_info=True)
            return result.to_dict()
        except Exception as exc:
            raise HTTPException(500, f"Web test failed: {exc}") from exc

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

    # ------------------------------------------------------------------
    # Desktop client
    # ------------------------------------------------------------------
    @app.post("/api/desktop/open-token")
    async def api_desktop_open_token(
        request: DesktopOpenTokenRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Generate a short-lived token used to launch the desktop client."""
        if request.project_id:
            _get_owned_project(request.project_id, current_user)
        token = DesktopTokenManager.create_open_token(
            user_id=current_user.user_id,
            project_id=request.project_id,
        )
        return {
            "token": token,
            "expires_in": 300,
            "project_id": request.project_id,
            "scheme_url": f"kyrozen://open?project_id={request.project_id or ''}&token={token}",
        }

    @app.post("/api/desktop/verify-token")
    async def api_desktop_verify_token(request: DesktopVerifyTokenRequest):
        """Exchange a short-lived open token or access token for long-lived credentials."""
        user_id: str | None = None
        project_id: str | None = None

        if request.token:
            open_data = DesktopTokenManager.consume_open_token(request.token)
            if open_data is None:
                raise HTTPException(401, "Invalid or expired open token")
            user_id = open_data["user_id"]
            project_id = open_data.get("project_id")
        elif request.access_token:
            config = _config or get_config()
            try:
                payload = _decode_supabase_token(request.access_token, config)
            except Exception as exc:
                raise HTTPException(401, f"Invalid access token: {exc}") from exc
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(401, "Invalid access token: missing user id")

        if not user_id:
            raise HTTPException(401, "Invalid token")

        credentials = DesktopTokenManager.create_credentials(user_id)

        manager = _get_desktop_manager()
        client = manager.register(
            user_id=user_id,
            device_name=request.device_name,
            client_version=request.client_version,
            platform=request.platform,
            current_project_id=project_id,
        )
        if _db is not None:
            try:
                _db.save_desktop_client(client.to_dict())
            except Exception as exc:
                get_logger(__name__).warning("Failed to persist desktop client", exc_info=True)

        return {
            "client_id": client.client_id,
            "refresh_token": credentials["refresh_token"],
            "ws_token": credentials["ws_token"],
            "access_token": request.access_token,
            "project_id": project_id,
            "user_id": user_id,
        }

    @app.get("/api/desktop/clients")
    async def api_list_desktop_clients(
        current_user: CurrentUser = Depends(get_current_user),
    ):
        manager = _get_desktop_manager()
        clients = manager.list_online_for_user(current_user.user_id)
        return {"clients": [c.to_dict() for c in clients]}

    @app.websocket("/ws/desktop")
    async def websocket_desktop(websocket: WebSocket):
        logger = get_logger(_config.log_level if _config else "info")
        await websocket.accept()
        client: DesktopClient | None = None

        try:
            auth_message = await websocket.receive_json()
            if auth_message.get("type") != "auth":
                await websocket.close(code=1008, reason="First message must be auth")
                return

            ws_token = auth_message.get("token", "")
            user_id = DesktopTokenManager.verify_ws_token(ws_token)
            if user_id is None:
                await websocket.close(code=1008, reason="Invalid websocket token")
                return

            manager = _get_desktop_manager()
            client = manager.register(
                user_id=user_id,
                device_name=auth_message.get("device_name", "Unknown Device"),
                client_version=auth_message.get("client_version", ""),
                platform=auth_message.get("platform", ""),
                current_project_id=auth_message.get("current_project_id"),
                websocket=websocket,
            )
            if _db is not None:
                try:
                    _db.save_desktop_client(client.to_dict())
                except Exception as exc:
                    logger.warning("Failed to persist desktop client on connect", exc_info=True)

            await websocket.send_json({
                "type": "auth_success",
                "client_id": client.client_id,
                "user_id": user_id,
            })

            while True:
                message = await websocket.receive_json()
                msg_type = message.get("type")

                if msg_type == "heartbeat":
                    manager.touch(client.client_id)
                    current_project = message.get("current_project_id")
                    if current_project:
                        manager.update_project(client.client_id, current_project)
                    if _db is not None:
                        try:
                            _db.save_desktop_client(client.to_dict())
                        except Exception as exc:
                            logger.warning("Failed to persist desktop client heartbeat", exc_info=True)
                    await websocket.send_json({"type": "heartbeat_ack", "timestamp": _utc_now_iso()})

                elif msg_type == "task_accepted":
                    task_id = message.get("task_id")
                    if task_id and _db is not None:
                        task = _db.get_task(task_id)
                        if task is not None:
                            task.assigned_client_id = client.client_id
                            task.update_status("running")
                            _db.save_task(task)
                    await websocket.send_json({"type": "task_accepted_ack", "task_id": task_id})

                elif msg_type == "task_step":
                    task_id = message.get("task_id")
                    step = message.get("step")
                    if task_id and step and _db is not None:
                        task = _db.get_task(task_id)
                        if task is not None:
                            from kyrozen.core.task import TaskStep
                            task.steps.append(TaskStep(**step))
                            _db.save_task(task)

                elif msg_type == "task_result":
                    task_id = message.get("task_id")
                    status = message.get("status")
                    result = message.get("result")
                    if task_id and _db is not None:
                        task = _db.get_task(task_id)
                        if task is not None:
                            task.result = result
                            if status in {"completed", "failed", "cancelled"}:
                                task.update_status(status)
                            _db.save_task(task)

                elif msg_type == "confirmation_response":
                    # TODO: wire into running agent confirmation queue
                    logger.info(f"Confirmation response for task {message.get('task_id')}: {message.get('confirmed')}")

                elif msg_type == "model_request":
                    asyncio.create_task(_handle_model_request(websocket, message, user_id, logger))

                else:
                    logger.warning(f"Unknown desktop websocket message type: {msg_type}")

        except WebSocketDisconnect:
            logger.info("Desktop client disconnected")
        except Exception as exc:
            logger.warning(f"Desktop websocket error: {exc}")
        finally:
            if client is not None:
                manager.unregister(client.client_id)
                if _db is not None:
                    try:
                        _db.save_desktop_client(client.to_dict())
                    except Exception as exc:
                        logger.warning("Failed to persist desktop client disconnect", exc_info=True)
                try:
                    await websocket.close()
                except Exception:
                    pass

    return app


app = create_app()
