"""FastAPI web server and REST API for Kyrozen Core testing."""

from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
import re
import shutil
import secrets
from contextlib import asynccontextmanager
import traceback
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
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
from kyrozen.core.stagegate import StageGateStore, advance as advance_stage, compute_gate, refresh_gate, sync_artifact_deliverables
from kyrozen.desktop import DesktopClientManager, DesktopTokenManager, QuotaManager
from kyrozen.development.agent import SoftwareDevelopmentAgent
from kyrozen.discovery import ProblemDiscoveryAgent
from kyrozen.hardware.agent import HardwareDevelopmentAgent
from kyrozen.hardware.transport import build_connection_model
from kyrozen.logs import get_logger
from kyrozen.memory import InMemoryMemory, JsonFileMemory, ProjectMemory
from kyrozen.membership import MembershipService
from kyrozen.membership.afdian import AfdianClient, AfdianError
from kyrozen.models import ModelInterface, get_model_provider
from kyrozen.planning.agent import ProductPlanningAgent
from kyrozen.project import KyrozenDatabase, ProjectContextBuilder, ProjectManager, SupabaseDatabase, create_database
from kyrozen.project.project import PROJECT_STAGES
from kyrozen.project.workflow import PROJECT_TYPES, WORKFLOW_VERSION, classify_project_type, stages_for, tracks_for
from kyrozen.planning.models import SolutionComparison, PHASE2_COMPARISON_DIMENSIONS
from kyrozen.research.agent import MarketResearchAgent
from kyrozen.research.runs import execute_research_run
from kyrozen.tools.research.providers import (
    CommunitySearchProvider,
    CrowdfundingSearchProvider,
    GitHubSearchProvider,
    GitHubDiscussionsProvider,
    PatentSearchProvider,
    RedditSearchProvider,
    SemanticScholarProvider,
    TavilySearchProvider,
    SerperSearchProvider,
)
from kyrozen.discovery.evidence import Evidence
from kyrozen.phase2 import build_workbench_snapshot


def _encode_github_oauth_state(
    redirect_uri: str, secret: str, ttl_seconds: int = 600,
    user_id: str | None = None, desktop: bool = False,
) -> str:
    """Create a short-lived signed OAuth state that survives process changes."""
    payload: dict[str, Any] = {
        "redirect_uri": redirect_uri,
        "exp": int(datetime.now(timezone.utc).timestamp()) + ttl_seconds,
        "nonce": uuid.uuid4().hex,
    }
    if user_id:
        payload["user_id"] = user_id
    if desktop:
        payload["desktop"] = True
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    signed = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{encoded}.{signed}"


def _decode_github_oauth_state(state: str, secret: str) -> dict[str, Any] | None:
    """Validate and decode a signed OAuth state without server-local storage."""
    try:
        encoded, supplied_signature = state.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        expected_signature = base64.urlsafe_b64encode(expected).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            return None
        if not payload.get("redirect_uri"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
from kyrozen.testing.agent import TestingAgent
from kyrozen.learning.agent import LearningAgent
from kyrozen.learning.repository import LearningRepository
from kyrozen.tools import get_default_registry
from kyrozen.web.waitlist import WaitlistStore
from kyrozen.api.rate_limit import auth_limiter, waitlist_limiter, _client_ip


# Global state managed via lifespan
_agent_factory: "AgentFactory | None" = None
_config: KyrozenConfig | None = None
_db: KyrozenDatabase | SupabaseDatabase | None = None
_project_manager: ProjectManager | None = None
_context_builder: ProjectContextBuilder | None = None
_learning_repository: LearningRepository | None = None
_desktop_manager: DesktopClientManager | None = None
_quota_manager: QuotaManager | None = None
_membership_service: MembershipService | None = None
_waitlist_store: WaitlistStore | None = None


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


class CommitMessageRequest(BaseModel):
    project_id: str | None = Field(None, description="Project ID for authorization and context")
    changed_files: list[str] = Field(default_factory=list, max_length=200)


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    name: str | None = None


class SigninRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class WaitlistRequest(BaseModel):
    email: str = Field(..., min_length=1)
    source: str = Field("website", max_length=100)


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


class DesktopPollPairingRequest(BaseModel):
    code: str = Field(..., min_length=1)


class GithubDesktopExchangeRequest(BaseModel):
    code: str = Field(..., min_length=16, max_length=256)


class DesktopConfirmPairingRequest(BaseModel):
    code: str = Field(..., min_length=1)


class ToolExecuteRequest(BaseModel):
    tool: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    goal: str = ""
    budget: str = ""
    initial_idea: str = ""
    project_type: str = Field("software", pattern="^(software|embedded|hybrid)$")


class MembershipPlanRequest(BaseModel):
    plan: str = Field(..., pattern="^(free|lite|pro|ultimate|enterprise)$")


class MembershipSeatRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


class AfdianCheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(lite|pro|ultimate)$")


class MembershipPaymentReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(open|resolved|rejected)$")
    reason: str = ""


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    goal: str | None = None
    budget: str | None = None
    status: str | None = None
    current_stage: str | None = None
    next_steps: str | None = None
    risks: list[str] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    project_type: str | None = Field(default=None, pattern="^(software|embedded|hybrid)$")
    workflow_version: str | None = None
    type_source: str | None = None
    type_confidence: str | None = Field(default=None, pattern="^(low|medium|high)$")
    type_confirmed: bool | None = None


class RefreshSessionRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


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
    expected_version: int | None = Field(default=None, ge=1)


class CreateEvidenceRequest(BaseModel):
    claim: str = Field(..., min_length=1)
    original_text: str = ""
    summary: str = ""
    source: str = Field("user_statement", pattern="^(user_statement|ai_inference|external_evidence)$")
    source_name: str = ""
    evidence_type: str = Field("interview", pattern="^(interview|observation|survey|screenshot|video|public_source|user_statement|ai_inference|external_evidence)$")
    verified: bool = False
    confidence: str = Field("medium", pattern="^(low|medium|high)$")
    notes: str = ""
    source_url: str = ""
    observed_at: str = ""
    target_audience: str = ""
    related_question: str = ""
    counter_evidence: list[str] = Field(default_factory=list)
    claim_type: str = Field("unknown", pattern="^(fact|opinion|inference|unknown)$")


class UpdateEvidenceRequest(BaseModel):
    claim: str | None = Field(default=None, min_length=1)
    original_text: str | None = None
    summary: str | None = None
    verified: bool | None = None
    confidence: str | None = Field(default=None, pattern="^(low|medium|high)$")
    notes: str | None = None
    source_url: str | None = None
    target_audience: str | None = None
    related_question: str | None = None
    counter_evidence: list[str] | None = None
    claim_type: str | None = Field(default=None, pattern="^(fact|opinion|inference|unknown)$")
    status: str | None = Field(default=None, pattern="^(active|invalid|merged|deleted)$")
    expected_version: int | None = Field(default=None, ge=1)


class MergeEvidenceRequest(BaseModel):
    target_evidence_id: str = Field(..., min_length=1)
    reason: str = ""
    expected_source_version: int | None = Field(default=None, ge=1)
    expected_target_version: int | None = Field(default=None, ge=1)


class ResearchRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class ResearchSourceRequest(BaseModel):
    source: dict[str, Any]
    expected_version: int | None = Field(default=None, ge=1)


class SolutionComparisonRequest(BaseModel):
    comparison: dict[str, Any]
    action: str = Field("save", pattern="^(save|select|compose|reject|regenerate|revoke)$")
    affected_tasks: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    expected_version: int | None = Field(default=None, ge=1)


class ProtocolConfirmationRequest(BaseModel):
    protocol: dict[str, Any]
    confirmed: bool = True
    affected_files: list[str] = Field(default_factory=list)
    affected_tasks: list[str] = Field(default_factory=list)
    expected_version: int | None = Field(default=None, ge=1)


class WorkflowTrackAdvanceRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)


class UpdateDefectRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved|verified|rejected)$")
    owner: str | None = None
    fix: str | None = None
    regression_result_id: str | None = None
    reproduction_steps: list[str] | None = None
    actual: str | None = None
    expected: str | None = None
    expected_version: int | None = Field(default=None, ge=1)


class StageSyncRequest(BaseModel):
    stage: str = Field(..., min_length=1)
    progress: int = Field(0, ge=0, le=100)
    gate: dict[str, Any] = Field(default_factory=dict)


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
    participant_id: str = Field("", max_length=120)
    user_type: str = ""
    task: str = ""
    completed: bool | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    blockers: list[str] = Field(default_factory=list)
    quote: str = ""
    satisfaction: int | None = Field(default=None, ge=1, le=5)


class CreateEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    project_id: str | None = None


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


def _get_membership_service() -> MembershipService:
    if _membership_service is None:
        raise RuntimeError("Membership service not initialized")
    return _membership_service


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


def _is_developer_account(current_user: CurrentUser) -> bool:
    """Check the internal developer entitlement from config and GitHub claims."""
    config = _config
    if config is None:
        return False
    if config.provider == "mock":
        return True
    if current_user.user_id in config.developer_user_ids:
        return True
    metadata = current_user.raw_claims.get("user_metadata", {}) or {}
    github_user = str(
        metadata.get("github_username")
        or metadata.get("preferred_username")
        or metadata.get("user_name")
        or ""
    ).casefold()
    return github_user in {name.casefold() for name in config.developer_github_users}


def _is_developer_user_id(user_id: str) -> bool:
    config = _config
    return bool(config and (config.provider == "mock" or user_id in config.developer_user_ids))


def _membership_plan_override(current_user: CurrentUser) -> str | None:
    """Return the plan usable in this release for an ordinary account."""
    if _is_developer_account(current_user):
        return None
    if _config is not None and not _config.membership_enabled:
        return "free"
    return None


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _is_openable_external_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


#: Modes preferring local (desktop) execution. Phase 1 acceptance: when a
#: desktop client is online, ALL project chat modes run locally so save_*
#: tools write deliverables (docs/PROBLEM.md, docs/MARKET.md, PRD.md, ...)
#: into the user's real workspace and the local stage gate can detect them.
#: When no desktop client is online, the task still falls back to server-side
#: execution (see the `routed` checks in /api/chat).
_LOCAL_FIRST_MODES = {
    "discovery",
    "problem_discovery",
    "market_research",
    "research",
    "planning",
    "product_definition",
    "solution_design",
    "development",
    "hardware",
    "hardware_development",
    "testing",
    "iteration",
    "learning",
}


def _requires_local_client(mode: str) -> bool:
    """Return True for modes that prefer the local desktop client."""
    return mode in _LOCAL_FIRST_MODES


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
    developer: bool = False,
) -> None:
    """Proxy a model request from a desktop client to the configured cloud model.

    Sends chunks back as model_stream_chunk messages. Enforces the per-user
    token quota before executing the request and records actual usage after.
    """
    request_id = message.get("request_id")
    messages = message.get("messages", [])
    stream = message.get("stream", True)

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

    membership = _get_membership_service()
    estimate = membership.estimate(
        prompt_tokens=_estimate_tokens("".join(str(m.get("content", "")) for m in messages)),
        completion_tokens=0,
        provider=getattr(model, "provider_name", ""),
        model=getattr(model, "model", ""),
    )
    if not developer:
        decision = membership.check(user_id, estimate, plan_override="free" if _config is not None and not _config.membership_enabled else None)
        if not decision["allowed"]:
            await websocket.send_json({
                "type": "model_error",
                "request_id": request_id,
                "error": decision["reason"],
                "quota": decision,
                "graceful_closing": bool(decision.get("graceful")),
            })
            return

    try:
        if not stream:
            response = await asyncio.to_thread(model.chat, messages)
            prompt_tokens = response.usage.prompt_tokens if response.usage else _estimate_tokens("".join(m.get("content", "") for m in messages))
            completion_tokens = response.usage.completion_tokens if response.usage else _estimate_tokens(response.content)
            usage = membership.estimate(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, provider=getattr(model, "provider_name", ""), model=getattr(model, "model", ""))
            membership.record_usage(user_id, usage, kind="model", provider=getattr(model, "provider_name", ""), model=getattr(model, "model", ""))
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
        usage = membership.estimate(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, provider=getattr(model, "provider_name", ""), model=getattr(model, "model", ""))
        membership.record_usage(user_id, usage, kind="model", provider=getattr(model, "provider_name", ""), model=getattr(model, "model", ""))
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


def _recommend_next_action(project: Any, stage: str | None = None) -> dict[str, str] | None:
    """Recommend the next action for a project's current or supplied stage."""
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
        "protocol_design": {
            "action": "确认软硬件协议",
            "reason": "混合项目必须先确认版本化消息和兼容边界",
            "target_mode": "planning",
        },
        "hardware_design": {
            "action": "设计硬件方案",
            "reason": "明确板卡、接线、电源和安全约束",
            "target_mode": "hardware_development",
        },
        "procurement": {
            "action": "整理 BOM 并记录采购状态",
            "reason": "硬件装配前需要确认型号、数量和替代件",
            "target_mode": "hardware_development",
        },
        "maker": {
            "action": "按 Maker 步骤装配",
            "reason": "逐步确认元件、动作、预期结果和安全提示",
            "target_mode": "hardware_development",
        },
        "firmware": {
            "action": "编译并准备上传固件",
            "reason": "固件必须在真实板卡测试前完成编译记录",
            "target_mode": "hardware_development",
        },
        "hardware_testing": {
            "action": "发现设备并进行硬件测试",
            "reason": "记录供电、串口、输入输出和恢复证据",
            "target_mode": "hardware_development",
        },
        "integration_testing": {
            "action": "运行软硬件集成测试",
            "reason": "验证协议、离线、重连、重复消息和版本兼容",
            "target_mode": "testing",
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
    return mapping.get(stage or project.current_stage)


def create_app(config: KyrozenConfig | None = None, model: ModelInterface | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _agent_factory, _config, _db, _project_manager, _context_builder, _learning_repository, _desktop_manager, _quota_manager, _membership_service, _waitlist_store
        _config = config or get_config()
        logger = get_logger(_config.log_level)
        issues = _config.validate()
        if issues:
            logger.error(f"Config issues: {'; '.join(issues)}")

        try:
            active_model = model if model is not None else get_model_provider(_config)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize model provider: {e}")
            active_model = None

        _db = create_database(_config)
        # P0-02: refuse to start (in production) if the desktop client schema is
        # missing, instead of failing on the first chat message at runtime.
        try:
            from kyrozen.db.schema_check import SchemaError, verify_desktop_schema

            verify_desktop_schema(_config)
        except SchemaError as se:
            if os.environ.get("KYROZEN_ALLOW_MISSING_SCHEMA") == "1":
                logger.warning(f"跳过数据库结构预检：{se}")
            else:
                logger.error(f"数据库结构预检失败，服务拒绝启动：{se}")
                raise
        except Exception as se:  # noqa: BLE001 - verification infra (network) issue
            logger.warning(f"无法完成数据库结构预检（将继续启动）：{se}")
        _project_manager = ProjectManager(_db, workspace_root=_config.workspace_root)
        _context_builder = ProjectContextBuilder(_project_manager, InMemoryMemory())
        os.makedirs(_config.workspace_root, exist_ok=True)
        _learning_repository = LearningRepository(_db)

        waitlist_db_path = str(Path(_config.workspace_root) / "waitlist.db")
        _waitlist_store = WaitlistStore(waitlist_db_path)

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
        _membership_service = MembershipService(_db, _config)
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

    @app.post("/api/waitlist")
    async def join_waitlist(
        request: Request,
        payload: WaitlistRequest,
        _rate_limit: None = Depends(waitlist_limiter.dependency(_client_ip)),
    ):
        if _waitlist_store is None:
            raise HTTPException(status_code=503, detail="Waitlist is not available")
        client_host = request.client.host if request.client else None
        result = _waitlist_store.add(payload.email, source=payload.source, ip=client_host)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Invalid request"))
        return {"success": True, "message": "已成功加入等待列表"}

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
    async def api_auth_signup(
        request: SignupRequest,
        _rate_limit: None = Depends(auth_limiter.dependency(_client_ip)),
    ):
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
    async def api_auth_signin(
        request: SigninRequest,
        _rate_limit: None = Depends(auth_limiter.dependency(_client_ip)),
    ):
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

    @app.post("/api/auth/refresh")
    async def api_auth_refresh(request: RefreshSessionRequest):
        """Exchange a Supabase refresh token without forcing GitHub login again."""
        config = get_config()
        if not config.supabase_url or not config.supabase_anon_key:
            raise HTTPException(status_code=500, detail="Supabase auth is not configured on the server")
        try:
            anon_client = create_client(config.supabase_url, config.supabase_anon_key)
            session = anon_client.auth.refresh_session(request.refresh_token)
            if not session.session or not session.session.access_token:
                raise ValueError("refresh did not return a session")
            return {
                "access_token": session.session.access_token,
                "refresh_token": session.session.refresh_token or request.refresh_token,
            }
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Session refresh failed: {exc}") from exc

    # ------------------------------------------------------------------
    # GitHub OAuth
    # ------------------------------------------------------------------

    class GitHubAuthorizeRequest(BaseModel):
        redirect_uri: str | None = None
        desktop: bool = False

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

        callback_uri = redirect_uri or config.github_oauth_redirect_uri or str(request.base_url).rstrip("/") + "/api/auth/github/callback"
        state = _encode_github_oauth_state(
            callback_uri, config.github_oauth_client_secret,
            user_id=current_user.user_id, desktop=desktop,
        )

        params = {
            "client_id": config.github_oauth_client_id,
            "redirect_uri": callback_uri,
            "state": state,
            "scope": "repo read:user user:email",
        }
        authorize_url = "https://github.com/login/oauth/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
        return {"authorize_url": authorize_url}

    @app.get("/api/auth/github/callback")
    async def api_github_callback(
        code: str,
        state: str,
    ):
        config = get_config()
        state_data = _decode_github_oauth_state(state, config.github_oauth_client_secret)
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
            # Serve an HTML page that auto-redirects to kyrozen:// but also
            # shows a manual "Open Kyrozen" button if the browser blocks it.
            redirect_url = f"kyrozen://auth/github?token={access_token}&scope={scope}"
            return HTMLResponse(
                status_code=200,
                content=f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>Kyrozen GitHub 授权</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; background: #f5f5f5; color: #333;
    }}
    .card {{
      background: white; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.08);
      padding: 36px 40px; max-width: 420px; width: 90%; text-align: center;
    }}
    .logo {{ font-size: 32px; margin-bottom: 12px; }}
    h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 8px; }}
    p {{ font-size: 14px; color: #666; margin-bottom: 20px; line-height: 1.5; }}
    .btn {{
      display: inline-block; padding: 12px 28px; border-radius: 8px;
      font-size: 15px; font-weight: 500; cursor: pointer; text-decoration: none;
      transition: background 0.15s; margin: 6px;
    }}
    .btn-primary {{ background: #7c3aed; color: white; border: none; }}
    .btn-primary:hover {{ background: #6d28d9; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🔗</div>
    <h1>正在连接 GitHub…</h1>
    <p id="status">如果浏览器未能自动打开应用，请点击下方按钮。</p>
    <a class="btn btn-primary" id="open-btn" href="{redirect_url}">打开 Kyrozen</a>
  </div>
  <script>
    setTimeout(function () {{ window.location.href = "{redirect_url}"; }}, 200);
    setTimeout(function () {{
      document.getElementById("status").textContent =
        "浏览器已阻止自动跳转。请手动点击下方按钮打开 Kyrozen。";
    }}, 1200);
  </script>
</body>
</html>""",
            )
        return {
            "success": True,
            "scope": scope,
            "desktop": is_desktop,
        }

    # ------------------------------------------------------------------
    # GitHub Login (no prior Kyrozen account required)
    # ------------------------------------------------------------------
    _github_login_states: dict[str, dict[str, Any]] = {}
    # OAuth credentials never travel through a custom-scheme URL. The browser
    # receives only this short-lived, one-time opaque code.
    _github_desktop_exchange_codes: dict[str, dict[str, Any]] = {}

    def _cleanup_github_login_states() -> None:
        now = datetime.now(timezone.utc).timestamp()
        expired = [k for k, v in _github_login_states.items() if v.get("expires_at", 0) < now]
        for k in expired:
            _github_login_states.pop(k, None)
        expired_exchange = [k for k, v in _github_desktop_exchange_codes.items() if v.get("expires_at", 0) < now]
        for k in expired_exchange:
            _github_desktop_exchange_codes.pop(k, None)

    @app.get("/api/auth/github/login")
    async def api_github_login(request: Request):
        """Start GitHub OAuth login. No prior Kyrozen account is required.

        Returns a GitHub authorize URL.  After the user authorizes, GitHub
        redirects to /api/auth/github/login-callback, which creates (or finds)
        a Kyrozen account and redirects the desktop app via kyrozen://.
        """
        config = get_config()
        if not config.github_oauth_client_id or not config.github_oauth_client_secret:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on the server")

        callback_uri = (
            config.github_oauth_redirect_uri
            or str(request.base_url).rstrip("/") + "/api/auth/github/login-callback"
        )
        state = _encode_github_oauth_state(callback_uri, config.github_oauth_client_secret)

        params = {
            "client_id": config.github_oauth_client_id,
            "redirect_uri": callback_uri,
            "state": state,
            "scope": "repo read:user user:email",
        }
        authorize_url = "https://github.com/login/oauth/authorize?" + urlencode(params)
        return {"authorize_url": authorize_url}

    @app.get("/api/auth/github/login-callback")
    async def api_github_login_callback(code: str, state: str):
        """GitHub OAuth callback – create (or find) a Kyrozen user, then
        redirect the desktop client with both a Kyrozen JWT and a GitHub token.
        """
        config = get_config()
        state_data = _decode_github_oauth_state(state, config.github_oauth_client_secret)
        if state_data is None:
            # Accept login attempts started immediately before this deployment.
            _cleanup_github_login_states()
            state_data = _github_login_states.pop(state, None)
        if not state_data:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

        if not config.github_oauth_client_id or not config.github_oauth_client_secret:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")

        try:
            import requests
        except ImportError as exc:
            raise HTTPException(status_code=500, detail=f"requests is not installed: {exc}") from exc

        # 1. Exchange code for GitHub access token
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
        github_token = token_data.get("access_token")
        if not github_token:
            raise HTTPException(status_code=502, detail=f"GitHub returned no token: {token_data}")
        scope = token_data.get("scope", "")

        # 2. Get GitHub user info
        user_resp = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        user_resp.raise_for_status()
        github_user = user_resp.json()
        github_username = github_user.get("login", "")
        github_name = github_user.get("name") or github_username

        # 2b. Resolve email — prefer /user/emails but gracefully fall back
        #     to the public email on /user (or a synthetic one) because the
        #     /user/emails endpoint requires the OAuth app to have email
        #     access enabled in its GitHub settings. Without that, GitHub
        #     returns 404 and the whole login fails.
        email = github_user.get("email")
        try:
            emails_resp = requests.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                primary = next((e for e in emails if e.get("primary")), None)
                email = (
                    primary["email"]
                    if primary
                    else (emails[0]["email"] if emails else email)
                ) or email
        except requests.RequestException:
            # Network error reaching GitHub — keep whatever we already have.
            pass
        if not email:
            email = f"{github_username}@github.com"

        # 3. Create or find Kyrozen user
        admin_client = create_client(config.supabase_url, config.supabase_service_role_key)
        random_password = uuid.uuid4().hex

        try:
            new_user = admin_client.auth.admin.create_user({
                "email": email,
                "password": random_password,
                "email_confirm": True,
                "user_metadata": {
                    "name": github_name,
                    "github_username": github_username,
                    "avatar_url": github_user.get("avatar_url", ""),
                    "github_access_token": github_token,
                    "github_token_scopes": scope,
                },
            })
            user_id = new_user.user.id
        except Exception:
            # User likely already exists – query by email and update
            r = requests.get(
                f"{config.supabase_url}/auth/v1/admin/users",
                headers={
                    "Authorization": f"Bearer {config.supabase_service_role_key}",
                    "apikey": config.supabase_service_role_key,
                },
                timeout=15,
            )
            r.raise_for_status()
            users_list = r.json().get("users", [])
            match = next((u for u in users_list if u.get("email") == email), None)
            if not match:
                raise HTTPException(status_code=500, detail="Failed to create or find user")
            user_id = match["id"]
            admin_client.auth.admin.update_user_by_id(
                user_id,
                {
                    "password": random_password,
                    "user_metadata": {
                        "name": github_name,
                        "github_username": github_username,
                        "avatar_url": github_user.get("avatar_url", ""),
                        "github_access_token": github_token,
                        "github_token_scopes": scope,
                    },
                },
            )

        # 4. Sign in to obtain a Kyrozen JWT
        auth_client = create_client(config.supabase_url, config.supabase_anon_key)
        session = auth_client.auth.sign_in_with_password({
            "email": email,
            "password": random_password,
        })
        kyrozen_token = session.session.access_token
        refresh_token = session.session.refresh_token

        # 5. Store sensitive credentials behind a short-lived one-time code.
        _cleanup_github_login_states()
        exchange_code = secrets.token_urlsafe(32)
        _github_desktop_exchange_codes[exchange_code] = {
            "access_token": kyrozen_token,
            "refresh_token": refresh_token,
            "github_token": github_token,
            "scope": scope,
            "user_id": user_id,
            "expires_at": datetime.now(timezone.utc).timestamp() + 120,
        }

        # 6. Redirect desktop via kyrozen:// with only the opaque code.
        #    Serve an HTML page that auto-redirects but also shows a
        #    manual "Open Kyrozen" button if the browser blocks the
        #    custom protocol handler.
        redirect_url = f"kyrozen://auth/login?code={exchange_code}"
        return HTMLResponse(
            status_code=200,
            content=f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>Kyrozen 登录</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; background: #f5f5f5; color: #333;
    }}
    .card {{
      background: white; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.08);
      padding: 36px 40px; max-width: 420px; width: 90%; text-align: center;
    }}
    .logo {{ font-size: 32px; margin-bottom: 12px; }}
    h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 8px; }}
    p {{ font-size: 14px; color: #666; margin-bottom: 20px; line-height: 1.5; }}
    .btn {{
      display: inline-block; padding: 12px 28px; border-radius: 8px;
      font-size: 15px; font-weight: 500; cursor: pointer; text-decoration: none;
      transition: background 0.15s; margin: 6px;
    }}
    .btn-primary {{ background: #7c3aed; color: white; border: none; }}
    .btn-primary:hover {{ background: #6d28d9; }}
    .btn-outline {{ background: white; color: #7c3aed; border: 2px solid #7c3aed; }}
    .btn-outline:hover {{ background: #f5f3ff; }}
    .copied {{ background: #34d399 !important; color: white !important; border-color: #34d399 !important; }}
    .note {{ font-size: 12px; color: #999; margin-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🔐</div>
    <h1>正在打开 Kyrozen…</h1>
    <p id="status">如果浏览器未能自动打开应用，请点击下方按钮。</p>
    <a class="btn btn-primary" id="open-btn" href="{redirect_url}">打开 Kyrozen</a>
    <br>
    <button class="btn btn-outline" id="copy-btn" onclick="copyLink()">复制登录链接</button>
    <p class="note" id="copy-note" style="display:none">链接已复制，请在 Safari 地址栏中粘贴打开。</p>
  </div>

  <script>
    // Auto-redirect via location — most browsers allow this once user clicked "Login".
    setTimeout(function () {{
      window.location.href = "{redirect_url}";
    }}, 200);

    // If the page is still visible after 1s, the redirect was blocked.
    setTimeout(function () {{
      document.getElementById("status").textContent =
        "浏览器已阻止自动跳转。请手动点击下方按钮打开 Kyrozen。";
      document.getElementById("open-btn").style.display = "inline-block";
    }}, 1200);

    function copyLink() {{
      navigator.clipboard.writeText("{redirect_url}").then(function () {{
        var btn = document.getElementById("copy-btn");
        btn.textContent = "已复制！";
        btn.classList.add("copied");
        document.getElementById("copy-note").style.display = "block";
      }});
    }}
  </script>
</body>
</html>""",
        )

    @app.post("/api/auth/github/desktop-exchange")
    async def api_github_desktop_exchange(request: GithubDesktopExchangeRequest):
        """Consume a one-time desktop OAuth code over HTTPS."""
        _cleanup_github_login_states()
        payload = _github_desktop_exchange_codes.pop(request.code, None)
        if not payload or payload.get("expires_at", 0) < datetime.now(timezone.utc).timestamp():
            raise HTTPException(status_code=400, detail="Invalid or expired desktop OAuth code")
        return {
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "github_token": payload["github_token"],
            "scope": payload.get("scope", ""),
            "user_id": payload.get("user_id", ""),
        }

    # ------------------------------------------------------------------
    # Desktop update signatures
    # ------------------------------------------------------------------
    _UPDATE_SIGNATURES_PATH = Path(__file__).resolve().parents[2] / "releases" / "signatures.json"

    def _load_update_signatures() -> dict[str, Any]:
        try:
            with open(_UPDATE_SIGNATURES_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            get_logger(__name__).warning("Invalid update signatures file: %s", exc)
            return {}

    @app.get("/api/desktop/updates/signatures")
    async def api_desktop_update_signatures(version: str, filename: str | None = None):
        """Return update package signatures for the requested version.

        The desktop client verifies the downloaded installer against these
        signatures before allowing installation. This endpoint is intentionally
        public so the updater can query it before the user logs in.
        """
        signatures = _load_update_signatures()
        version_data = signatures.get(version)
        if not version_data:
            raise HTTPException(status_code=404, detail="Version not found")

        files = version_data.get("files", {})
        if filename:
            file_data = files.get(filename)
            if not file_data:
                raise HTTPException(status_code=404, detail="File not found")
            return {
                "version": version,
                "filename": filename,
                "sha512": file_data.get("sha512"),
                "signature": file_data.get("signature"),
                "release_date": version_data.get("releaseDate"),
            }

        return {
            "version": version,
            "release_date": version_data.get("releaseDate"),
            "files": files,
        }

    @app.get("/api/desktop/updates/latest")
    async def api_desktop_update_latest():
        """Return the latest available desktop update version metadata."""
        signatures = _load_update_signatures()
        if not signatures:
            raise HTTPException(status_code=404, detail="No update signatures available")

        # Versions are expected to follow semantic versioning.
        latest_version = max(signatures.keys(), key=lambda v: tuple(int(x) for x in v.split(".") if x.isdigit()))
        latest = signatures[latest_version]
        return {
            "version": latest_version,
            "release_date": latest.get("releaseDate"),
            "files": list(latest.get("files", {}).keys()),
        }

    @app.get("/api/user/github-status")
    async def api_user_github_status(current_user: CurrentUser = Depends(get_current_user)):
        metadata = current_user.raw_claims.get("user_metadata", {}) or {}
        token = metadata.get("github_access_token")
        return {
            "connected": bool(token),
            "scope": metadata.get("github_token_scopes", ""),
        }

    @app.get("/api/user/github-token")
    async def api_user_github_token(current_user: CurrentUser = Depends(get_current_user)):
        """Return the GitHub access token stored in Supabase user metadata.

        The desktop client uses this endpoint to restore the GitHub token after
        a restart, so it can commit and push without re-authorizing every time.
        """
        metadata = current_user.raw_claims.get("user_metadata", {}) or {}
        token = metadata.get("github_access_token")
        if not token:
            raise HTTPException(status_code=404, detail="GitHub token not found")
        return {
            "token": token,
            "scope": metadata.get("github_token_scopes", ""),
        }

    @app.post("/api/user/github-token")
    async def api_user_store_github_token(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Store or update the GitHub access token in Supabase user metadata.

        This allows the desktop client to push a token obtained via the
        kyrozen:// auth callback into Supabase metadata when the backend
        callback flow cannot update it directly.
        """
        config = get_config()
        if not config.supabase_url or not config.supabase_service_role_key:
            raise HTTPException(status_code=503, detail="Supabase admin not configured")
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
        token = body.get("token")
        scope = body.get("scope", "")
        if not token or not isinstance(token, str):
            raise HTTPException(status_code=400, detail="token is required")
        try:
            from supabase import create_client
            admin_client = create_client(config.supabase_url, config.supabase_service_role_key)
            admin_client.auth.admin.update_user_by_id(
                current_user.user_id,
                {
                    "user_metadata": {
                        "github_access_token": token,
                        "github_token_scopes": scope,
                    }
                },
            )
        except Exception as exc:
            get_logger(__name__).warning("Failed to store GitHub token: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to store GitHub token") from exc
        return {"success": True}

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
        if not _is_developer_account(current_user):
            estimate = _get_membership_service().estimate(
                prompt_tokens=max(1, len(request.message) // 4),
                completion_tokens=0,
            )
            decision = _get_membership_service().check(
                current_user.user_id,
                estimate,
                conversation=True,
                plan_override=_membership_plan_override(current_user),
            )
            if not decision["allowed"]:
                raise HTTPException(429, decision["reason"])
            # Count the user-initiated conversation separately from model usage;
            # this keeps the monthly conversation limit from double-counting
            # the Desktop model proxy call while still making the reservation
            # durable before the agent starts.
            _get_membership_service().record_usage(
                current_user.user_id,
                _get_membership_service().estimate(prompt_tokens=0),
                kind="conversation",
            )
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

            # Planning requests originate from the desktop decision center.
            # Route them to the already-connected local Agent before building
            # the large cloud context.  Context construction can require many
            # artifact reads and exceed the desktop's request timeout even
            # though the desktop is online and able to execute the task.  The
            # local agent receives the project id and rebuilds its own scoped
            # context, while the task remains observable through WebSocket.
            if request.mode == "planning":
                task = agent.task_manager.create(
                    title=request.message[:60],
                    description=request.message,
                    project_id=request.project_id,
                    mode=request.mode,
                    requires_local_client=True,
                )
                routed = await _route_task_to_desktop(task, current_user.user_id)
                if routed:
                    return {
                        "task_id": task.id,
                        "status": task.status,
                        "project_id": request.project_id,
                        "mode": request.mode,
                        "dispatched_to_desktop": True,
                    }

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
                return ""
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
                    return {
                        "task_id": task.id,
                        "status": task.status,
                        "project_id": request.project_id,
                        "mode": request.mode,
                        "dispatched_to_desktop": True,
                    }

            agent.run_task(task, user_input, confirmed=request.confirmed)
            if task.status == "failed" or (task.status == "completed" and not _assistant_content(task).strip()):
                task_errors = list(getattr(task, "errors", []) or [])
                detail = str(task_errors[-1] if task_errors else "模型服务暂时不可用，请稍后重试。")
                raise HTTPException(status_code=502, detail=detail)
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
            return {
                "task_id": task.id,
                "status": task.status,
                "project_id": request.project_id,
                "mode": request.mode,
                "content": _assistant_content(task),
                "steps": [step.to_dict() for step in task.steps],
            }
        except HTTPException:
            raise
        except Exception as e:
            if request.project_id and user_message is not None:
                pm.save_chat_message(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": current_user.user_id,
                        "project_id": request.project_id,
                        "role": "assistant",
                        "content": "任务执行失败，请重试。",
                        "metadata": {"error_type": type(e).__name__},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            raise HTTPException(500, f"Agent error: {e}") from e

    @app.post("/api/git/commit-message")
    async def api_generate_commit_message(
        request: CommitMessageRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Ask the configured LLM for a concise commit subject line.

        This endpoint deliberately does not create a chat message or perform
        any Git operation. The desktop only uses the returned text to populate
        the commit input for the user's review.
        """
        if request.project_id:
            _get_owned_project(request.project_id, current_user)
        agent = _get_agent()
        if agent.model is None:
            raise HTTPException(503, "Model provider not configured")

        files = [str(item).strip() for item in request.changed_files if str(item).strip()]
        if not files:
            raise HTTPException(400, "没有检测到文件变更")
        files_text = "\n".join(f"- {item[:240]}" for item in files[:200])
        response = await asyncio.to_thread(
            agent.model.chat,
            [
                {
                    "role": "system",
                    "content": (
                        "你是 Git 提交信息助手。根据变更文件列表生成一条简洁的 Conventional Commit subject。"
                        "只能返回一行英文提交信息，格式为 type: description；不要返回引号、Markdown、解释、换行或正文。"
                        "type 只能使用 feat、fix、refactor、docs、test、chore、style、perf。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"请为以下变更生成提交信息：\n{files_text}",
                },
            ],
        )
        message = str(response.content or "").strip()
        message = re.sub(r"^```(?:text|bash|git)?\s*|\s*```$", "", message, flags=re.IGNORECASE).strip()
        message = re.sub(r"^(?:提交信息|commit message)\s*[:：]\s*", "", message, flags=re.IGNORECASE)
        message = message.splitlines()[0].strip().strip("`\"'")
        if not message:
            raise HTTPException(502, "模型没有生成有效的提交信息")
        return {"message": message[:120]}

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
        if not _is_developer_account(current_user):
            existing = pm.list(user_id=current_user.user_id)
            allowed, reason = _get_membership_service().project_decision(
                current_user.user_id,
                len(existing),
                plan_override=_membership_plan_override(current_user),
            )
            if not allowed:
                raise HTTPException(status_code=403, detail=reason)
        project = pm.create(
            name=request.name,
            description=request.description,
            goal=request.goal,
            budget=request.budget,
            initial_idea=request.initial_idea,
            user_id=current_user.user_id,
            project_type=request.project_type,
        )
        # Ensure project directory and memory file exist
        if _config is not None:
            os.makedirs(_config.project_dir(project.id), exist_ok=True)
            _project_memory(project.id)
        if not _is_developer_account(current_user):
            _get_membership_service().record_project_creation(current_user.user_id, project.id)
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
        project = _get_owned_project(project_id, current_user)
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        if "current_stage" in updates and updates["current_stage"] != project.current_stage:
            raise HTTPException(409, "阶段不能通过普通项目更新跳转，请使用统一阶段门禁")
        if "project_type" in updates:
            raise HTTPException(409, "项目类型必须通过 workflow-confirm 确认，不能通过普通项目更新修改")
        if updates.get("status") == "completed":
            readiness = build_workbench_snapshot(project, pm).get("phase2_completion", {})
            if not readiness.get("ready"):
                raise HTTPException(
                    409,
                    detail={"message": "第二阶段验收条件尚未全部满足，不能标记项目完成", "phase2_completion": readiness},
                )
        project = pm.update(project_id, **updates)
        if project is None:
            raise HTTPException(404, "Project not found")
        return project.to_dict()

    @app.post("/api/projects/{project_id}/stage-sync")
    async def api_sync_project_stage(
        project_id: str,
        request: StageSyncRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Persist a stage already advanced by the local StageGateStore.

        The desktop Agent remains the gate authority for the user's selected
        workspace. The server only accepts one adjacent stage and a gate
        snapshot, so this endpoint cannot be used as an arbitrary index jump.
        """
        project = _get_owned_project(project_id, current_user)
        stages = list(stages_for(project.project_type))
        if request.stage not in stages:
            raise HTTPException(422, "阶段不属于当前项目流程")
        current_index = stages.index(project.current_stage)
        target_index = stages.index(request.stage)
        if target_index < current_index or target_index > current_index + 1:
            raise HTTPException(409, "阶段只能由统一门禁逐步推进")
        if target_index == current_index + 1:
            gate = request.gate
            missing = gate.get("missing") if isinstance(gate.get("missing"), list) else None
            gate_stage = gate.get("stage")
            gate_index = gate.get("index")
            if (
                gate_stage != request.stage
                or gate_index != target_index
                or gate.get("can_advance") is not True
                or missing is None
                or any(
                    isinstance(item, dict)
                    and item.get("kind") not in {"confirmation"}
                    and item.get("required", True)
                    and not item.get("satisfied", False)
                    for item in missing
                )
            ):
                raise HTTPException(409, "缺少完整且自洽的本地阶段门禁证据")
            # Do not treat the client snapshot as the authority. Rebuild the
            # gate from the server's project workspace and persisted records so
            # a caller cannot advance with {can_advance: true, missing: []}.
            workflow_root = Path(_config.project_dir(project_id) if _config is not None else f".kyrozen/projects/{project_id}")
            server_store = StageGateStore(
                workflow_root / ".kyrozen" / "stagegate.json",
                project_id=project_id,
                project_type=project.project_type,
            )
            server_store.set_workflow(project.project_type)
            server_store.current_stage = project.current_stage
            solution_artifact = _get_project_manager().get_latest_artifact(
                project_id, "solution_decision", title="Solution Decision"
            )
            solution_confirmed = False
            if solution_artifact is not None:
                try:
                    solution_confirmed = json.loads(solution_artifact.content).get("action") in {"select", "compose"}
                except (TypeError, json.JSONDecodeError):
                    solution_confirmed = False
            server_store.record_confirmation(
                "solution_confirmed",
                solution_confirmed,
                detail="用户已确认方案" if solution_confirmed else "尚未确认有效方案",
            )
            actual_gate = refresh_gate(server_store, workflow_root)
            sync_artifact_deliverables(
                server_store,
                [artifact.type for artifact in _get_project_manager().list_artifacts(project_id)],
            )
            server_store.save()
            actual_gate = compute_gate(server_store)
            actual_missing = [
                item for item in actual_gate.missing
                if item.kind not in {"confirmation", "task"} and item.required and not item.satisfied
            ]
            if not actual_gate.can_advance or actual_missing:
                raise HTTPException(
                    409,
                    detail={
                        "message": "服务端重新计算的阶段门禁未满足",
                        "gate": actual_gate.to_dict(),
                    },
                )
        updated = _get_project_manager().update(
            project_id,
            current_stage=request.stage,
            progress=request.progress,
            next_steps=(_recommend_next_action(project, request.stage) or {}).get("action", ""),
            blocked_reason="",
        )
        if updated is None:
            raise HTTPException(404, "Project not found")
        return {**updated.to_dict(), "gate": request.gate}

    @app.get("/api/projects/{project_id}/workflow-suggestion")
    async def api_project_workflow_suggestion(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        return {
            **classify_project_type(goal=project.goal, description=project.description),
            "current": {
                "project_type": project.project_type,
                "workflow_version": project.workflow_version,
                "type_confirmed": project.type_confirmed,
            },
        }

    @app.post("/api/projects/{project_id}/workflow-confirm")
    async def api_confirm_project_workflow(
        project_id: str,
        request: UpdateProjectRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        if not request.project_type:
            raise HTTPException(422, "project_type is required")
        if project.current_stage != "problem_discovery" and project.project_type != request.project_type:
            raise HTTPException(409, "项目类型只能在问题探索阶段确认或重新评估")
        updated = _get_project_manager().update(
            project_id,
            project_type=request.project_type,
            workflow_version=WORKFLOW_VERSION,
            type_source=request.type_source or "user_confirmed",
            type_confidence=request.type_confidence or "high",
            type_confirmed=True,
        )
        if updated is None:
            raise HTTPException(404, "Project not found")
        return {**updated.to_dict(), "workflow_stages": list(stages_for(updated.project_type))}

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
            "project_type": project.project_type,
            "workflow_version": project.workflow_version,
            "workflow_stages": list(stages_for(project.project_type)),
            "stage": project.current_stage,
            "progress": project.progress,
            "blocked_reason": project.blocked_reason or None,
            "next_action": next_action,
        }

    # ------------------------------------------------------------------
    # Phase 2 workbench: durable evidence and a single refreshable projection
    # ------------------------------------------------------------------
    @app.get("/api/projects/{project_id}/phase2/workbench")
    async def api_phase2_workbench(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        return build_workbench_snapshot(project, _get_project_manager())

    @app.post("/api/projects/{project_id}/phase2/tracks/{track}/advance")
    async def api_advance_hybrid_track(
        project_id: str,
        track: str,
        request: WorkflowTrackAdvanceRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        if project.project_type != "hybrid":
            raise HTTPException(409, "只有混合项目支持独立并行轨道")
        track_definitions = tracks_for("hybrid")
        if track not in track_definitions:
            raise HTTPException(422, detail={"message": "未知的混合项目轨道", "track": track})
        pm = _get_project_manager()
        title = "Hybrid Workflow Track State"
        current = pm.get_latest_artifact(project_id, "workflow_track_state", title=title)
        if request.expected_version is not None and (current is None or current.version != request.expected_version):
            raise HTTPException(409, detail={"message": "混合轨道状态已变化，请刷新后重试", "current_version": current.version if current else None})
        try:
            state = json.loads(current.content) if current else {}
        except (TypeError, json.JSONDecodeError):
            state = {}
        tracks = state.get("tracks") if isinstance(state.get("tracks"), dict) else {}
        for name, stages in track_definitions.items():
            saved = tracks.get(name) if isinstance(tracks.get(name), dict) else {}
            tracks[name] = {
                "state": str(saved.get("state") or "pending"),
                "stages": list(stages),
                "current_stage": saved.get("current_stage"),
                "completed_stages": list(saved.get("completed_stages") or []),
                "next_stage": saved.get("next_stage") if "next_stage" in saved else (stages[0] if stages else None),
            }
        selected = tracks[track]
        solution = pm.get_latest_artifact(project_id, "solution_decision", title="Solution Decision")
        try:
            solution_confirmed = solution is not None and json.loads(solution.content).get("action") in {"select", "compose"}
        except (TypeError, json.JSONDecodeError):
            solution_confirmed = False
        comparison = pm.get_latest_artifact(project_id, "solution_comparison", title="Solution Comparison")
        try:
            comparison_valid = comparison is not None and not SolutionComparison.from_dict(json.loads(comparison.content)).phase2_validation_errors()
        except (TypeError, json.JSONDecodeError, ValueError):
            comparison_valid = False
        if not solution_confirmed or not comparison_valid:
            raise HTTPException(409, "尚未确认方案，不能启动混合项目并行轨道")
        if track == "protocol":
            protocol = pm.get_latest_artifact(project_id, "protocol_confirmation", title="Versioned Protocol")
            try:
                protocol_confirmed = protocol is not None and json.loads(protocol.content).get("confirmed") is True
            except (TypeError, json.JSONDecodeError):
                protocol_confirmed = False
            if not protocol_confirmed:
                raise HTTPException(409, "尚未确认版本化协议，不能启动协议轨道")
        if track == "integration":
            unfinished = [
                name for name in ("software", "hardware", "protocol")
                if tracks[name].get("state") != "completed"
            ]
            if unfinished:
                raise HTTPException(409, detail={"message": "软件、硬件和协议轨道必须先完成，才能启动集成轨道", "unfinished_tracks": unfinished})
        if selected["state"] == "completed":
            raise HTTPException(409, "该混合项目轨道已经完成")
        stages = selected["stages"]
        current_stage = selected.get("current_stage")
        completed = list(selected.get("completed_stages") or [])
        if current_stage is None:
            selected["state"] = "active"
            selected["current_stage"] = stages[0] if stages else None
            selected["next_stage"] = stages[1] if len(stages) > 1 else None
        else:
            requirements = {
                "testing": {"test_plan", "test_result"},
                "hardware_design": {"hardware_architecture", "wiring_design"},
                "procurement": {"bom"},
                "maker": {"assembly_step"},
                # Compile/upload/monitor are persisted as local hardware run
                # evidence and are finally required by hardware_acceptance;
                # the track itself must at least have a durable firmware
                # project definition.
                "firmware": {"firmware_project"},
                "hardware_testing": {"hardware_acceptance"},
                "integration_testing": {"protocol_scenarios", "integration_test", "test_result"},
            }
            required = requirements.get(str(current_stage), set())
            artifact_types = {artifact.type for artifact in pm.list_artifacts(project_id)}
            if required and not required.issubset(artifact_types):
                raise HTTPException(409, detail={"message": "当前轨道仍缺少交付物", "track": track, "stage": current_stage, "required_artifacts": sorted(required - artifact_types)})
            if current_stage not in completed:
                completed.append(current_stage)
            index = stages.index(current_stage)
            if index + 1 >= len(stages):
                selected["state"] = "completed"
                selected["current_stage"] = current_stage
                selected["next_stage"] = None
            else:
                selected["state"] = "active"
                selected["current_stage"] = stages[index + 1]
                selected["next_stage"] = stages[index + 2] if index + 2 < len(stages) else None
        selected["completed_stages"] = completed
        content = {"workflow_version": project.workflow_version, "tracks": tracks, "updated_by": current_user.user_id, "updated_at": _utc_now_iso()}
        artifact = pm.save_artifact(project_id, "workflow_track_state", title, json.dumps(content, ensure_ascii=False, indent=2), "推进混合项目并行轨道")
        return {"track": track, "state": selected, "tracks": tracks, "artifact_id": artifact.id, "version": artifact.version}

    @app.get("/api/projects/{project_id}/evidence")
    async def api_list_evidence(
        project_id: str,
        include_invalid: bool = False,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        items = build_workbench_snapshot(_get_owned_project(project_id, current_user), _get_project_manager())["evidence"]["items"]
        if not include_invalid:
            items = [item for item in items if item.get("status", "active") == "active"]
        return items

    @app.get("/api/projects/{project_id}/evidence/{artifact_id}/impact")
    async def api_evidence_impact(
        project_id: str,
        artifact_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Show references that would change before invalidating or merging evidence."""
        _get_owned_project(project_id, current_user)
        pm = _get_project_manager()
        artifact = pm.get_artifact(project_id, artifact_id)
        if artifact is None or artifact.type != "discovery_evidence":
            raise HTTPException(404, "Evidence not found")
        latest: dict[tuple[str, str], Any] = {}
        for candidate in pm.list_artifacts(project_id):
            key = (candidate.type, candidate.title)
            if candidate.version >= getattr(latest.get(key), "version", -1):
                latest[key] = candidate
        affected = []
        for candidate in latest.values():
            if candidate.id == artifact_id:
                continue
            if artifact_id not in candidate.content:
                continue
            category = {
                "problem_brief": "Problem Brief",
                "market_research_report": "研究结论",
                "research_source": "研究来源",
                "solution_comparison": "方案比较",
                "solution_decision": "方案决策",
            }.get(candidate.type, candidate.type)
            affected.append({
                "artifact_id": candidate.id,
                "type": candidate.type,
                "title": candidate.title,
                "version": candidate.version,
                "category": category,
            })
        return {"evidence_id": artifact_id, "affected": affected, "count": len(affected)}

    @app.post("/api/projects/{project_id}/evidence")
    async def api_create_evidence(
        project_id: str,
        request: CreateEvidenceRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        evidence = Evidence(**request.model_dump())
        artifact = _get_project_manager().save_artifact(
            project_id=project_id,
            type="discovery_evidence",
            title=f"Evidence: {evidence.claim[:40]}",
            content=json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2),
            change_reason="Evidence recorded from Phase 2 workbench",
        )
        data = evidence.to_dict()
        data.update({"artifact_id": artifact.id, "version": artifact.version, "title": artifact.title})
        return data

    @app.patch("/api/projects/{project_id}/evidence/{artifact_id}")
    async def api_update_evidence(
        project_id: str,
        artifact_id: str,
        request: UpdateEvidenceRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        pm = _get_project_manager()
        artifact = pm.get_artifact(project_id, artifact_id)
        if artifact is None or artifact.type != "discovery_evidence":
            raise HTTPException(404, "Evidence not found")
        if request.expected_version is not None and artifact.version != request.expected_version:
            raise HTTPException(409, detail={"message": "证据版本已变化，请刷新后重试", "current_version": artifact.version})
        try:
            evidence = Evidence.from_dict(json.loads(artifact.content))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, f"Stored evidence is invalid: {exc}") from exc
        for key, value in request.model_dump(exclude_none=True, exclude={"expected_version"}).items():
            setattr(evidence, key, value)
        evidence.__post_init__()
        updated = pm.save_artifact(
            project_id=project_id,
            type=artifact.type,
            title=artifact.title,
            content=json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2),
            change_reason="Evidence updated in Phase 2 workbench",
        )
        data = evidence.to_dict()
        data.update({"artifact_id": updated.id, "version": updated.version, "title": updated.title})
        return data

    @app.post("/api/projects/{project_id}/evidence/{artifact_id}/merge")
    async def api_merge_evidence(
        project_id: str,
        artifact_id: str,
        request: MergeEvidenceRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Merge evidence while rewriting durable references to the target item."""
        _get_owned_project(project_id, current_user)
        pm = _get_project_manager()
        source = pm.get_artifact(project_id, artifact_id)
        target = pm.get_artifact(project_id, request.target_evidence_id)
        if source is None or source.type != "discovery_evidence":
            raise HTTPException(404, "Source evidence not found")
        if target is None or target.type != "discovery_evidence":
            raise HTTPException(404, "Target evidence not found")
        if source.id == target.id:
            raise HTTPException(422, "不能将证据合并到自身")
        if request.expected_source_version is not None and source.version != request.expected_source_version:
            raise HTTPException(409, detail={"message": "源证据版本已变化，请刷新后重试", "current_version": source.version})
        if request.expected_target_version is not None and target.version != request.expected_target_version:
            raise HTTPException(409, detail={"message": "目标证据版本已变化，请刷新后重试", "current_version": target.version})

        def replace_reference(value: Any) -> Any:
            if isinstance(value, str):
                return value.replace(source.id, target.id)
            if isinstance(value, list):
                return [replace_reference(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_reference(item) for key, item in value.items()}
            return value

        rewritten: list[dict[str, Any]] = []
        latest: dict[tuple[str, str], Any] = {}
        for candidate in pm.list_artifacts(project_id):
            key = (candidate.type, candidate.title)
            if candidate.version >= getattr(latest.get(key), "version", -1):
                latest[key] = candidate
        for candidate in latest.values():
            if candidate.id in {source.id, target.id} or source.id not in candidate.content:
                continue
            try:
                parsed = json.loads(candidate.content)
            except (TypeError, json.JSONDecodeError):
                continue
            replaced = replace_reference(parsed)
            if replaced == parsed:
                continue
            updated = pm.save_artifact(
                project_id=project_id,
                type=candidate.type,
                title=candidate.title,
                content=json.dumps(replaced, ensure_ascii=False, indent=2),
                change_reason=f"Evidence merged: {source.id} -> {target.id}",
            )
            rewritten.append({"artifact_id": updated.id, "type": updated.type, "title": updated.title, "version": updated.version})

        source_data = Evidence.from_dict(json.loads(source.content))
        source_data.status = "merged"
        source_data.notes = f"已合并到证据 {target.id}" + (f"；{request.reason}" if request.reason else "")
        merged_source = pm.save_artifact(
            project_id=project_id,
            type=source.type,
            title=source.title,
            content=json.dumps(source_data.to_dict(), ensure_ascii=False, indent=2),
            change_reason="Evidence merged into another evidence item",
        )
        return {
            "source": {**source_data.to_dict(), "artifact_id": merged_source.id, "version": merged_source.version},
            "target_evidence_id": target.id,
            "rewritten": rewritten,
            "count": len(rewritten),
        }

    @app.post("/api/projects/{project_id}/evidence/{artifact_id}/restore")
    async def api_restore_evidence(
        project_id: str,
        artifact_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        return await api_update_evidence(
            project_id,
            artifact_id,
            UpdateEvidenceRequest(status="active"),
            current_user,
        )

    @app.delete("/api/projects/{project_id}/evidence/{artifact_id}")
    async def api_delete_evidence(
        project_id: str,
        artifact_id: str,
        expected_version: int | None = None,
        confirm_impact: bool = False,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Versioned soft-delete with an explicit impact confirmation.

        Evidence remains in the immutable Artifact history and can be restored;
        the endpoint never physically removes project data.
        """
        _get_owned_project(project_id, current_user)
        impact = await api_evidence_impact(project_id, artifact_id, current_user)
        if not confirm_impact:
            raise HTTPException(
                409,
                detail={
                    "message": "删除前请确认受影响的 Problem Brief、研究结论和方案引用",
                    "impact": impact,
                },
            )
        return await api_update_evidence(
            project_id,
            artifact_id,
            UpdateEvidenceRequest(status="deleted", expected_version=expected_version),
            current_user,
        )

    @app.post("/api/projects/{project_id}/research/runs")
    async def api_run_research(
        project_id: str,
        request: ResearchRunRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        config = _config
        providers = [
            TavilySearchProvider(getattr(config, "tavily_api_key", "") if config else ""),
            SerperSearchProvider(getattr(config, "serper_api_key", "") if config else ""),
            GitHubSearchProvider(getattr(config, "github_token", "") if config else ""),
            SemanticScholarProvider(getattr(config, "semantic_scholar_api_key", "") if config else ""),
            PatentSearchProvider(getattr(config, "patent_search_url", "") if config else ""),
            CrowdfundingSearchProvider(getattr(config, "crowdfunding_search_url", "") if config else ""),
            CommunitySearchProvider(),
            RedditSearchProvider(),
            GitHubDiscussionsProvider(getattr(config, "github_token", "") if config else ""),
        ]
        run = execute_research_run(
            request.query,
            providers,
            run_id=f"research_{uuid.uuid4().hex[:10]}",
            limit=request.limit,
        )
        pm = _get_project_manager()
        run_artifact = pm.save_artifact(
            project_id=project_id,
            type="research_run",
            title=f"Research Run {run.run_id}",
            content=json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
            change_reason="Multi-source research run",
        )
        for source in run.sources:
            pm.save_artifact(
                project_id=project_id,
                type="research_source",
                title=f"Research Source: {source.url or source.title[:80]}",
                content=json.dumps(source.to_dict(), ensure_ascii=False, indent=2),
                change_reason=f"Collected by {run.run_id}",
            )
        return {**run.to_dict(), "artifact_id": run_artifact.id, "version": run_artifact.version}

    @app.get("/api/projects/{project_id}/research/runs")
    async def api_list_research_runs(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        runs = []
        for artifact in _get_project_manager().list_artifacts(project_id):
            if artifact.type != "research_run":
                continue
            try:
                data = json.loads(artifact.content)
            except json.JSONDecodeError:
                continue
            data.update({"artifact_id": artifact.id, "version": artifact.version})
            runs.append(data)
        return sorted(runs, key=lambda item: item.get("run_id", ""), reverse=True)

    @app.post("/api/projects/{project_id}/research/sources")
    async def api_save_research_source(
        project_id: str,
        request: ResearchSourceRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        from kyrozen.research.models import ResearchSource

        try:
            source = ResearchSource.from_dict(request.source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not _is_openable_external_url(source.url):
            raise HTTPException(422, "研究来源必须提供可打开的绝对 HTTP(S) URL")
        pm = _get_project_manager()
        title = f"Research Source: {source.url or source.title[:80]}"
        current = pm.get_latest_artifact(project_id, "research_source", title=title)
        if request.expected_version is not None and (current is None or current.version != request.expected_version):
            raise HTTPException(409, detail={"message": "研究来源版本已变化，请刷新后重试", "current_version": current.version if current else None})
        artifact = pm.save_artifact(
            project_id=project_id,
            type="research_source",
            title=title,
            content=json.dumps(source.to_dict(), ensure_ascii=False, indent=2),
            change_reason="Research source edited",
        )
        return {**source.to_dict(), "artifact_id": artifact.id, "version": artifact.version}

    @app.get("/api/projects/{project_id}/solutions")
    async def api_get_solution_comparison(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        artifact = _get_project_manager().get_latest_artifact(project_id, "solution_comparison", title="Solution Comparison")
        if artifact is None:
            return {"comparison": None, "confirmed": False}
        try:
            comparison = SolutionComparison.from_dict(json.loads(artifact.content))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(422, f"方案比较无法解析: {exc}") from exc
        decision_artifact = _get_project_manager().get_latest_artifact(project_id, "solution_decision", title="Solution Decision")
        confirmed = False
        if decision_artifact is not None:
            try:
                confirmed = json.loads(decision_artifact.content).get("action") in {"select", "compose"}
            except (TypeError, json.JSONDecodeError):
                confirmed = False
        return {
            "comparison": comparison.to_dict(),
            "validation_errors": comparison.phase2_validation_errors(),
            "confirmed": confirmed,
            "artifact_id": artifact.id,
            "version": artifact.version,
        }

    @app.post("/api/projects/{project_id}/solutions")
    async def api_save_solution_comparison(
        project_id: str,
        request: SolutionComparisonRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        current_artifact = _get_project_manager().get_latest_artifact(project_id, "solution_comparison", title="Solution Comparison")
        if request.expected_version is not None:
            if current_artifact is None or current_artifact.version != request.expected_version:
                raise HTTPException(409, detail={"message": "方案版本已变化，请刷新后重试", "current_version": current_artifact.version if current_artifact else None})
        try:
            comparison = SolutionComparison.from_dict(request.comparison)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        referenced_evidence_ids = sorted({
            evidence_id
            for solution in comparison.solutions
            for evidence_id in solution.evidence_ids
            if str(evidence_id).strip()
        })
        missing_evidence_ids = [
            evidence_id
            for evidence_id in referenced_evidence_ids
            if (pm_artifact := _get_project_manager().get_artifact(project_id, evidence_id)) is None
            or pm_artifact.type != "discovery_evidence"
        ]
        if missing_evidence_ids:
            raise HTTPException(422, detail={
                "message": "方案引用了不存在或不属于当前项目的证据",
                "missing_evidence_ids": missing_evidence_ids,
            })
        if request.action in {"select", "compose"}:
            # A draft comparison may be saved while research is still in
            # progress, but a user confirmation is the irreversible gate into
            # implementation. Every selected candidate must point to an
            # existing problem evidence record, and the project must contain
            # at least one real, openable research source. This prevents a
            # generic Artifact write or a synthetic three-candidate payload
            # from bypassing the evidence -> research -> decision loop.
            missing_candidate_refs = [
                solution.name or f"方案 {index + 1}"
                for index, solution in enumerate(comparison.solutions)
                if not any(str(evidence_id).strip() for evidence_id in solution.evidence_ids)
            ]
            if missing_candidate_refs:
                raise HTTPException(422, detail={
                    "message": "确认方案前，每个候选方案至少需要引用一条问题证据",
                    "missing_candidate_evidence": missing_candidate_refs,
                })
            real_research_source = False
            for candidate in _get_project_manager().list_artifacts(project_id):
                if candidate.type not in {"research_source", "market_research_report"}:
                    continue
                try:
                    payload = json.loads(candidate.content)
                except (TypeError, json.JSONDecodeError):
                    continue
                sources = payload.get("sources", []) if candidate.type == "market_research_report" else [payload]
                if any(
                    isinstance(source, dict)
                    and _is_openable_external_url(source.get("url"))
                    and not any(marker in str(source.get("title", "")).lower() for marker in ("not configured", "search failed", "rate limited"))
                    for source in sources
                ):
                    real_research_source = True
                    break
            if not real_research_source:
                raise HTTPException(422, detail={
                    "message": "确认方案前必须先保存至少一条真实、可打开的市场研究来源",
                })
        if request.action == "regenerate":
            # Regeneration is intentionally agent-provided: the API does not
            # invent market evidence or candidate solutions. It persists the
            # new candidate set and its lineage so the desktop can safely
            # present a fresh comparison before confirmation.
            comparison.regeneration_count = (comparison.regeneration_count or 0) + 1
            comparison.regenerated_from_version = current_artifact.version if current_artifact else None
        errors = comparison.phase2_validation_errors()
        if errors and request.action in {"save", "select", "compose"}:
            raise HTTPException(422, detail={"message": "方案比较尚未满足第二阶段门禁", "errors": errors})
        pm = _get_project_manager()
        impact_artifact = None
        artifact = pm.save_artifact(
            project_id=project_id,
            type="solution_comparison",
            title="Solution Comparison",
            content=json.dumps(comparison.to_dict(), ensure_ascii=False, indent=2),
            change_reason=f"Solution comparison action: {request.action}",
        )
        if request.action in {"select", "compose"}:
            decision = pm.add_decision(
                project_id=project_id,
                decision=f"Solution {request.action}: {comparison.recommendation}",
                reason=comparison.recommendation_reason,
                alternatives=[solution.name for solution in comparison.solutions],
                source="user",
            )
            impact_targets = [
                {"key": "prd", "artifact_type": "product_definition", "title": "PRD", "applicable": True},
                {"key": "technical_plan", "artifact_type": "technical_plan", "title": "Technical Plan", "applicable": True},
                {"key": "procurement", "artifact_type": "hardware_bom", "title": "Bill of Materials", "applicable": project.project_type in {"embedded", "hybrid"}},
                {"key": "testing", "artifact_type": "test_plan", "title": "Test Plan", "applicable": True},
                {"key": "file_tasks", "artifact_type": "file_task", "title": "Solution File Tasks", "applicable": True},
            ]
            generated_tasks: list[dict[str, Any]] = []
            task_manager = _get_agent().task_manager
            existing_tasks = task_manager.list_tasks(project_id=project_id)
            for target in impact_targets:
                if not target["applicable"]:
                    continue
                task_title = f"方案影响：更新{target['title']}"
                task = next((item for item in existing_tasks if item.title == task_title and item.status not in {"completed", "cancelled"}), None)
                if task is None:
                    task = task_manager.create(
                        title=task_title,
                        description=f"方案 {comparison.recommendation} 已确认；请根据方案决策更新 {target['title']}。",
                        project_id=project_id,
                        mode="planning" if target["key"] in {"prd", "technical_plan"} else "testing" if target["key"] == "testing" else "hardware_development" if target["key"] == "procurement" else "development",
                    )
                generated_tasks.append({"id": task.id, "title": task.title, "status": task.status, "target": target["key"]})
            impact = {
                "decision_id": decision.id,
                "action": request.action,
                "recommendation": comparison.recommendation,
                "affected_files": list(request.affected_files),
                "requested_tasks": list(request.affected_tasks),
                "targets": impact_targets,
                "generated_tasks": generated_tasks,
            }
            impact_artifact = pm.save_artifact(
                project_id=project_id,
                type="solution_impact",
                title="Solution Impact Tasks",
                content=json.dumps(impact, ensure_ascii=False, indent=2),
                change_reason="Generated affected PRD, technical plan, procurement, testing and file tasks",
            )
            pm.save_artifact(
                project_id=project_id,
                type="solution_decision",
                title="Solution Decision",
                content=json.dumps({"action": request.action, "decision_id": decision.id, "affected_tasks": request.affected_tasks, "affected_files": request.affected_files, "impact_artifact_id": impact_artifact.id, "generated_task_ids": [item["id"] for item in generated_tasks]}, ensure_ascii=False, indent=2),
                change_reason="User confirmed solution decision",
            )
        elif request.action in {"reject", "revoke"}:
            cancelled_task_ids: list[str] = []
            previous_decision = pm.get_latest_artifact(project_id, "solution_decision", title="Solution Decision")
            if previous_decision is not None:
                try:
                    previous_data = json.loads(previous_decision.content)
                except (TypeError, json.JSONDecodeError):
                    previous_data = {}
                task_manager = _get_agent().task_manager
                for task_id in previous_data.get("generated_task_ids", []):
                    task = task_manager.get(str(task_id))
                    if task is None or task.project_id != project_id:
                        continue
                    # A completed task is historical evidence and must not be
                    # rewritten. Pending/running confirmation work generated
                    # by the revoked decision is explicitly stopped.
                    if task.status in {"pending", "running", "waiting_confirmation"}:
                        task.update_status("cancelled")
                        task_manager.update(task)
                        cancelled_task_ids.append(task.id)
            pm.save_artifact(
                project_id=project_id,
                type="solution_decision",
                title="Solution Decision",
                content=json.dumps({"action": request.action, "affected_tasks": request.affected_tasks, "cancelled_task_ids": cancelled_task_ids}, ensure_ascii=False, indent=2),
                change_reason="Solution decision revoked or rejected",
            )
        # Mirror the decision into the local gate used by the desktop Agent.
        # The artifact remains the durable source of truth; this record only
        # lets offline stage actions enforce the same hard prerequisite.
        try:
            if _config is not None:
                root = Path(_config.project_dir(project_id))
                gate_store = StageGateStore(
                    root / ".kyrozen" / "stagegate.json",
                    project_id=project_id,
                    project_type=_get_owned_project(project_id, current_user).project_type,
                )
                gate_store.record_confirmation(
                    "solution_confirmed",
                    request.action in {"select", "compose"},
                    detail="用户已确认方案" if request.action in {"select", "compose"} else "方案确认已撤销",
                )
                gate_store.save()
        except Exception:
            # API persistence has already succeeded; a local desktop gate can
            # resynchronize from the artifact when it next advances/refreshes.
            pass
        return {"artifact_id": artifact.id, "version": artifact.version, "validation_errors": errors, "action": request.action, "impact_artifact_id": impact_artifact.id if impact_artifact else None}

    @app.post("/api/projects/{project_id}/protocol/confirm")
    async def api_confirm_protocol(
        project_id: str,
        request: ProtocolConfirmationRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        project = _get_owned_project(project_id, current_user)
        if project.project_type != "hybrid":
            raise HTTPException(409, "只有软硬件混合项目需要确认协议")
        protocol = dict(request.protocol)
        version = str(protocol.get("protocol_version") or "").strip()
        message_type = str(protocol.get("message_type") or "").strip()
        fields = protocol.get("fields")
        if not version or not message_type or not isinstance(fields, dict):
            raise HTTPException(422, "协议必须包含 protocol_version、message_type 和 fields")
        pm = _get_project_manager()
        current = pm.get_latest_artifact(project_id, "protocol_confirmation", title="Versioned Protocol")
        if request.expected_version is not None and (current is None or current.version != request.expected_version):
            raise HTTPException(409, detail={"message": "协议确认版本已变化，请刷新后重试", "current_version": current.version if current else None})
        previous_protocol: dict[str, Any] | None = None
        if current is not None:
            try:
                previous_content = json.loads(current.content)
                if isinstance(previous_content, dict) and isinstance(previous_content.get("protocol"), dict):
                    previous_protocol = previous_content["protocol"]
            except json.JSONDecodeError:
                previous_protocol = None
        protocol_changed = request.confirmed and previous_protocol != protocol
        generated_tasks: list[dict[str, Any]] = []
        impact_artifact = None
        if protocol_changed:
            task_manager = _get_agent().task_manager
            existing_tasks = task_manager.list_tasks(project_id=project_id)
            requested_targets = [f"文件：{item}" for item in request.affected_files]
            requested_targets.extend(f"任务：{item}" for item in request.affected_tasks)
            requested_targets.append("测试：验证协议版本、字段和兼容性")
            for target in requested_targets:
                title = f"协议影响：{target}"
                task = next((item for item in existing_tasks if item.title == title and item.status not in {"completed", "cancelled"}), None)
                if task is None:
                    task = task_manager.create(
                        title=title,
                        description=f"协议 {version} 已变化，请检查并更新 {target}。",
                        project_id=project_id,
                        mode="testing" if target.startswith("测试：") else "development",
                    )
                generated_tasks.append({"id": task.id, "title": task.title, "status": task.status})
            impact_artifact = pm.save_artifact(
                project_id=project_id,
                type="protocol_impact",
                title="Protocol Impact Tasks",
                content=json.dumps({
                    "protocol_version": version,
                    "previous_protocol": previous_protocol,
                    "protocol": protocol,
                    "affected_files": list(request.affected_files),
                    "affected_tasks": list(request.affected_tasks),
                    "generated_tasks": generated_tasks,
                }, ensure_ascii=False, indent=2),
                change_reason="Generated protocol change impact tasks and compatibility test",
            )
        content = {
            "protocol": protocol,
            "confirmed": request.confirmed,
            "affected_files": list(request.affected_files),
            "affected_tasks": list(request.affected_tasks),
            "protocol_changed": protocol_changed,
            "impact_artifact_id": impact_artifact.id if impact_artifact else None,
            "generated_task_ids": [item["id"] for item in generated_tasks],
        }
        artifact = pm.save_artifact(
            project_id=project_id,
            type="protocol_confirmation",
            title="Versioned Protocol",
            content=json.dumps(content, ensure_ascii=False, indent=2),
            change_reason="User confirmed versioned hybrid protocol" if request.confirmed else "User revoked versioned hybrid protocol",
        )
        if request.confirmed:
            connection_model = build_connection_model(
                protocol,
                affected_files=list(request.affected_files),
                affected_tasks=list(request.affected_tasks),
            )
            connection_artifact = pm.save_artifact(
                project_id=project_id,
                type="protocol_connection_model",
                title="Six-Layer Protocol Connection Model",
                content=json.dumps(connection_model, ensure_ascii=False, indent=2),
                change_reason="Persisted six-layer hybrid connection contract",
            )
        else:
            connection_artifact = None
        try:
            root = Path(_config.project_dir(project_id)) if _config is not None else Path(f".kyrozen/projects/{project_id}")
            store = StageGateStore(root / ".kyrozen" / "stagegate.json", project_id=project_id, project_type="hybrid")
            store.record_confirmation("protocol_design_confirmed", request.confirmed, detail=f"协议 {version} 已确认" if request.confirmed else "协议确认已撤销")
            store.save()
        except Exception:
            # The immutable artifact is authoritative; local gate sync will
            # recover the confirmation on the next desktop refresh.
            pass
        return {**content, "artifact_id": artifact.id, "version": artifact.version, "connection_model_artifact_id": connection_artifact.id if connection_artifact else None}

    @app.post("/api/projects/{project_id}/protocol/scenarios")
    async def api_run_protocol_scenarios(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Run and persist the deterministic six-case protocol simulator."""
        _get_owned_project(project_id, current_user)
        from kyrozen.hardware.transport import run_fake_protocol_scenarios

        result = run_fake_protocol_scenarios()
        artifact = _get_project_manager().save_artifact(
            project_id=project_id,
            type="protocol_scenarios",
            title="Protocol Scenario Run",
            content=json.dumps(result, ensure_ascii=False, indent=2),
            change_reason="Server-side deterministic protocol simulator",
        )
        return {**result, "artifact_id": artifact.id, "version": artifact.version}

    @app.get("/api/projects/{project_id}/chat")
    async def api_get_project_chat(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        pm = _get_project_manager()
        messages = pm.list_chat_messages(
            project_id=project_id,
            user_id=current_user.user_id,
        )
        # Desktop dispatch acknowledgements and legacy empty model replies are
        # transport state, not assistant answers. Keep them out of user chat.
        return [
            message for message in messages
            if not (
                message.get("role") == "assistant"
                and (
                    message.get("metadata", {}).get("dispatched_to_desktop")
                    or str(message.get("content", "")).strip().lower() in {"(no response)", "no response"}
                )
            )
        ]

    @app.post("/api/projects/{project_id}/advance")
    async def api_advance_project(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        pm = _get_project_manager()
        project = _get_owned_project(project_id, current_user)
        if project.current_stage == "problem_discovery" and not project.type_confirmed:
            raise HTTPException(409, "请先在问题探索阶段确认项目类型和对应流程")
        workflow_root = Path(_config.project_dir(project_id) if _config is not None else f".kyrozen/projects/{project_id}")
        store = StageGateStore(workflow_root / ".kyrozen" / "stagegate.json", project_id=project_id, project_type=project.project_type)
        store.set_workflow(project.project_type)
        # Keep the local gate's hard solution-decision condition synchronized
        # with the immutable artifact chain before evaluating the transition.
        # A rejected/revoked decision must not satisfy the implementation gate.
        solution_artifact = pm.get_latest_artifact(project_id, "solution_decision", title="Solution Decision")
        solution_confirmed = False
        if solution_artifact is not None:
            try:
                solution_action = json.loads(solution_artifact.content).get("action")
                solution_confirmed = solution_action in {"select", "compose"}
            except (TypeError, json.JSONDecodeError):
                solution_confirmed = False
        store.record_confirmation(
            "solution_confirmed",
            solution_confirmed,
            detail="用户已确认方案" if solution_confirmed else "尚未确认有效方案",
        )
        if project.current_stage in stages_for(project.project_type) and store.current_stage != project.current_stage:
            # Synchronize an already persisted cloud stage into the gate; the
            # transition itself is still performed only by advance_stage().
            store.current_stage = project.current_stage
        gate = refresh_gate(store, workflow_root)
        sync_artifact_deliverables(store, [artifact.type for artifact in pm.list_artifacts(project_id)])
        store.save()
        gate = compute_gate(store)
        stages = list(stages_for(project.project_type))
        if store.current_stage == stages[-1]:
            readiness = build_workbench_snapshot(project, pm).get("phase2_completion", {})
            if not readiness.get("ready"):
                raise HTTPException(
                    409,
                    detail={"message": "第二阶段验收条件尚未全部满足", "phase2_completion": readiness},
                )
            required_missing = [item for item in gate.missing if item.kind not in {"confirmation", "task"} and item.required]
            if required_missing:
                raise HTTPException(409, detail={"message": "阶段门禁未满足", "gate": gate.to_dict()})
            result = {"ok": True, "stage": store.current_stage, "gate": gate.to_dict()}
        else:
            result = advance_stage(store, "normal")
        if not result.get("ok"):
            raise HTTPException(409, detail={"message": result.get("error", "阶段门禁未满足"), "gate": result.get("gate", {})})
        new_stage = str(result.get("stage", store.current_stage))
        is_last = new_stage == stages[-1] and store.current_stage == new_stage
        next_action = _recommend_next_action(project, new_stage)
        updated = pm.update(
            project_id,
            current_stage=new_stage,
            progress=100 if is_last else int(store.progress),
            status="completed" if is_last else project.status,
            next_steps=next_action["action"] if next_action else "",
            blocked_reason="",
        )
        if updated is None:
            raise HTTPException(404, "Project not found")
        return {**updated.to_dict(), "gate": result.get("gate", {}), "workflow_stages": stages}

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
            if request.expected_version is not None:
                current = pm.get_latest_artifact(project_id, request.type, title=request.title)
                if current is None or current.version != request.expected_version:
                    raise HTTPException(409, detail={"message": "Artifact 版本已变化，请刷新后重试", "current_version": current.version if current else None})
            protected_gate_artifacts = {
                "solution_comparison": "方案比较接口",
                "solution_decision": "方案比较接口",
                "protocol_confirmation": "协议确认接口",
                "protocol_connection_model": "协议确认接口",
                "protocol_scenarios": "协议模拟器接口",
                "workflow_track_state": "混合轨道推进接口",
            }
            if request.type in protected_gate_artifacts:
                raise HTTPException(422, detail={"message": f"{request.type} 只能通过{protected_gate_artifacts[request.type]}写入"})
            if request.type == "validation_report":
                from kyrozen.testing.models import ValidationReport
                report = ValidationReport.from_dict(json.loads(request.content))
                validation_errors = report.phase2_validation_errors()
                if validation_errors:
                    raise HTTPException(422, detail={"message": "验证报告尚未满足第二阶段门禁", "errors": validation_errors})
            if request.type == "hardware_acceptance":
                # Keep the physical-evidence gate server-side as well as in
                # the desktop form. A generic Artifact write must not be able
                # to turn a BLOCKED/no-board run into a passed acceptance.
                payload = json.loads(request.content)
                required = {
                    "observed_behavior": "实际行为观察记录",
                    "confirmed_at": "用户确认时间",
                    "confirmation_answer": "Ask question 的用户回答",
                }
                missing = [label for key, label in required.items() if not str(payload.get(key, "")).strip()]
                if payload.get("confirmation_answer") != "confirmed_behavior_and_reconnect":
                    missing.append("Ask question 的明确肯定回答（符合，拔插后已恢复）")
                if payload.get("confirmed_by_user") is not True:
                    missing.append("用户明确确认")
                if payload.get("physical_evidence_required") is not True:
                    missing.append("实物证据标记")
                timestamps = payload.get("hardware_run_timestamps")
                if not isinstance(timestamps, list) or not timestamps:
                    missing.append("硬件运行记录引用")
                runs = payload.get("hardware_runs")
                if not isinstance(runs, list):
                    missing.append("硬件运行记录摘要")
                else:
                    successful_actions = {
                        str(run.get("action"))
                        for run in runs
                        if isinstance(run, dict) and run.get("status") == "PASSED" and run.get("success") is True
                    }
                    if not {"compile", "upload", "monitor"}.issubset(successful_actions):
                        missing.append("编译、上传和串口观察成功记录")
                    discoveries = [
                        run for run in runs
                        if isinstance(run, dict)
                        and run.get("action") == "list_ports"
                        and run.get("status") == "PASSED"
                        and run.get("success") is True
                        and run.get("board_detected") is True
                    ]
                    if len(discoveries) < 2:
                        missing.append("两次确认板卡的成功发现记录")
                if missing:
                    raise HTTPException(422, detail={"message": "实物验收证据不完整，仍应保持 BLOCKED", "missing": missing})
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
        participant_id = request.participant_id.strip() or current_user.user_id
        feedback = {
            "id": feedback_id,
            "user_id": current_user.user_id,
            "project_id": request.project_id,
            "type": request.type,
            "description": request.description,
            "priority": request.priority,
            "status": "open",
            "metadata": {
                "user_type": request.user_type,
                "task": request.task,
                "completed": request.completed,
                "duration_seconds": request.duration_seconds,
                "blockers": request.blockers,
                "quote": request.quote,
                "satisfaction": request.satisfaction,
                "participant_id": participant_id,
            },
            "created_at": now,
            "updated_at": now,
        }
        _db.save_feedback(feedback)
        # P0-19: also save as a project artifact so the canvas testing tab
        # can display user feedback after refresh.
        if request.project_id:
            try:
                pm = _get_project_manager()
                pm.save_artifact(
                    project_id=request.project_id,
                    type="user_feedback",
                    title=f"用户反馈 - {request.type} - {feedback_id}",
                    content=json.dumps({
                        "source_type": "manual",
                        "content": request.description,
                        "priority": request.priority,
                        "sentiment": "",
                        "problems": [],
                        "participant_id": participant_id,
                        "timestamp": now,
                        "user_type": request.user_type,
                        "task": request.task,
                        "completed": request.completed,
                        "duration_seconds": request.duration_seconds,
                        "blockers": request.blockers,
                        "quote": request.quote,
                        "satisfaction": request.satisfaction,
                    }, ensure_ascii=False),
                    change_reason="Manual user validation feedback recorded",
                )
            except Exception as exc:
                get_logger(__name__).warning("Failed to save feedback artifact: %s", exc)
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

    @app.get("/api/events")
    async def api_list_events(
        event_type: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        if _db is None:
            raise HTTPException(503, "Database not initialized")
        if project_id:
            _get_owned_project(project_id, current_user)
        events = _db.list_events(
            user_id=current_user.user_id,
            project_id=project_id,
            event_type=event_type,
            limit=max(1, min(limit, 1000)),
        )
        return {"events": events}

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

        def load_hardware_artifact(model: Any, artifact_type: str, title: str) -> tuple[Any, Any]:
            """Read a versioned hardware artifact without breaking the workbench.

            Older projects and partially written artifacts must not turn the
            read-only hardware projection into a 500.  Keep the artifact id
            when possible so the desktop can still show that the source was
            present, while falling back to an empty validated model.
            """
            latest = None
            try:
                latest = pm.get_latest_artifact(project_id, artifact_type, title=title)
                if latest is None:
                    return model(), None
                payload = json.loads(latest.content)
                if not isinstance(payload, dict):
                    raise ValueError("hardware artifact content must be a JSON object")
                return model.from_dict(payload), latest
            except Exception as exc:  # malformed legacy data must remain readable
                get_logger(__name__).warning(
                    f"Ignoring malformed hardware artifact {artifact_type} "
                    f"for {project_id}: {exc}"
                )
                return model(), latest

        arch, latest_arch = load_hardware_artifact(
            HardwareArchitecture, "hardware_architecture", "Hardware Architecture"
        )
        bom, latest_bom = load_hardware_artifact(BOM, "bom", "Bill of Materials")
        wiring, latest_wiring = load_hardware_artifact(
            WiringDesign, "wiring_design", "Wiring Design"
        )
        firmware, latest_firmware = load_hardware_artifact(
            FirmwareProject, "firmware_project", "Firmware Project"
        )

        assembly_steps = []
        debug_records = []
        try:
            hardware_artifacts = pm.list_artifacts(project_id)
        except Exception as exc:
            get_logger(__name__).warning(
                f"Unable to list hardware artifacts for {project_id}: {exc}"
            )
            hardware_artifacts = []
        for artifact in hardware_artifacts:
            try:
                payload = json.loads(artifact.content)
                if artifact.type == "assembly_step":
                    from kyrozen.hardware.models import AssemblyStep
                    assembly_steps.append(AssemblyStep.from_dict(payload))
                elif artifact.type == "hardware_debug_record":
                    from kyrozen.hardware.models import HardwareDebugRecord
                    debug_records.append(HardwareDebugRecord.from_dict(payload))
            except Exception as exc:
                get_logger(__name__).warning(
                    f"Ignoring malformed hardware record "
                    f"{getattr(artifact, 'id', 'unknown')} for {project_id}: {exc}"
                )

        try:
            decisions = [
                d for d in pm.list_decisions(project_id)
                if d.decision.startswith("Hardware decision:")
            ]
        except Exception as exc:
            get_logger(__name__).warning(
                f"Unable to list hardware decisions for {project_id}: {exc}"
            )
            decisions = []

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
            try:
                test_plan = TestPlan.from_dict(json.loads(latest_test_plan.content))
            except (json.JSONDecodeError, ValueError):
                pass

        test_results = []
        test_cases = []
        user_feedback = []
        for artifact in pm.list_artifacts(project_id):
            if artifact.type == "test_case":
                try:
                    from kyrozen.testing.models import TestCase
                    test_cases.append(TestCase.from_dict(json.loads(artifact.content)).to_dict())
                except (json.JSONDecodeError, ValueError):
                    pass
            elif artifact.type == "test_result":
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
            try:
                validation_report = ValidationReport.from_dict(json.loads(latest_validation.content))
            except (json.JSONDecodeError, ValueError):
                pass

        latest_iteration = pm.get_latest_artifact(
            project_id, "iteration_plan", title="Iteration Plan"
        )
        iteration_plan = {"items": [], "overall_recommendation": ""}
        if latest_iteration is not None:
            try:
                iteration_plan = json.loads(latest_iteration.content)
            except (json.JSONDecodeError, ValueError):
                pass

        decisions = [
            d for d in pm.list_decisions(project_id)
            if d.decision.startswith("Testing decision:") or d.decision.startswith("Validation decision:")
        ]

        participant_ids = {
            feedback.participant_id
            for feedback in user_feedback
            if feedback.participant_id
        }

        return {
            "project_id": project_id,
            "test_plan": test_plan.to_dict(),
            "test_cases": test_cases,
            "test_results": [r.to_dict() for r in test_results],
            "user_feedback": [fb.to_dict() for fb in user_feedback],
            "user_validation": {
                "participant_count": len(participant_ids),
                "completed_count": sum(1 for fb in user_feedback if fb.completed is True),
                "minimum_participants_met": len(participant_ids) >= 3,
            },
            "validation_report": validation_report.to_dict(),
            "iteration_plan": iteration_plan,
            "decisions": [d.to_dict() for d in decisions[-5:]],
            "latest_test_plan_artifact_id": latest_test_plan.id if latest_test_plan else None,
            "latest_validation_artifact_id": latest_validation.id if latest_validation else None,
            "latest_iteration_artifact_id": latest_iteration.id if latest_iteration else None,
        }

    @app.get("/api/projects/{project_id}/defects")
    async def api_project_defects(
        project_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        defects = []
        for artifact in _get_project_manager().list_artifacts(project_id):
            if artifact.type != "defect":
                continue
            try:
                item = json.loads(artifact.content)
            except json.JSONDecodeError:
                continue
            item.update({"artifact_id": artifact.id, "version": artifact.version})
            defects.append(item)
        return defects

    @app.patch("/api/projects/{project_id}/defects/{artifact_id}")
    async def api_update_defect(
        project_id: str,
        artifact_id: str,
        request: UpdateDefectRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        _get_owned_project(project_id, current_user)
        pm = _get_project_manager()
        artifact = pm.get_artifact(project_id, artifact_id)
        if artifact is None or artifact.type != "defect":
            raise HTTPException(404, "Defect not found")
        if request.expected_version is not None and artifact.version != request.expected_version:
            raise HTTPException(409, detail={"message": "缺陷版本已变化，请刷新后重试", "current_version": artifact.version})
        from kyrozen.testing.models import Defect
        try:
            defect = Defect.from_dict(json.loads(artifact.content))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, f"Stored defect is invalid: {exc}") from exc
        for key, value in request.model_dump(exclude_none=True, exclude={"expected_version"}).items():
            setattr(defect, key, value)
        if defect.regression_result_id:
            defect.status = "resolved"
        updated = pm.save_artifact(
            project_id=project_id,
            type="defect",
            title=artifact.title,
            content=json.dumps(defect.to_dict(), ensure_ascii=False, indent=2),
            change_reason="Defect status or regression updated",
        )
        return {**defect.to_dict(), "artifact_id": updated.id, "version": updated.version}

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
            access_token=current_user.access_token,
            developer=_is_developer_account(current_user),
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
        access_token: str | None = None
        developer = False

        if request.token:
            open_data = DesktopTokenManager.consume_open_token(request.token)
            if open_data is None:
                raise HTTPException(401, "Invalid or expired open token")
            user_id = open_data["user_id"]
            project_id = open_data.get("project_id")
            access_token = open_data.get("access_token")
            developer = bool(open_data.get("developer"))
        elif request.access_token:
            config = _config or get_config()
            try:
                payload = _decode_supabase_token(request.access_token, config)
            except Exception as exc:
                raise HTTPException(401, f"Invalid access token: {exc}") from exc
            user_id = payload.get("sub")
            access_token = request.access_token
            metadata = payload.get("user_metadata", {}) or {}
            github_user = str(metadata.get("github_username") or metadata.get("preferred_username") or metadata.get("user_name") or "").casefold()
            developer = bool(
                (_config and user_id in _config.developer_user_ids)
                or (_config and github_user in {name.casefold() for name in _config.developer_github_users})
            )
            if not user_id:
                raise HTTPException(401, "Invalid access token: missing user id")

        if not user_id:
            raise HTTPException(401, "Invalid token")

        credentials = DesktopTokenManager.create_credentials(
            user_id,
            developer=developer or _is_developer_user_id(user_id),
        )

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
            # A supplied JWT can be exchanged again after an API restart;
            # generated desktop tokens are retained for legacy open-token use.
            "access_token": access_token or credentials["api_token"],
            "project_id": project_id,
            "user_id": user_id,
        }

    @app.get("/api/desktop/quota")
    async def api_desktop_quota(
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Return membership information without blocking project stages."""
        developer = _is_developer_account(current_user)
        if developer:
            return {
                "allowed": True,
                "reason": "Developer unlimited",
                "used": 0,
                "limit": 0,
                "remaining": -1,
                "plan": "developer",
                "project_limit": 0,
                "weekly_credit_limit": 0,
                "conversation_limit": 0,
            }
        status = _get_membership_service().status(
            current_user.user_id,
            plan_override=_membership_plan_override(current_user),
        )
        project_limit = {"free": 1, "lite": 5, "pro": 20, "ultimate": 0, "enterprise": 0}.get(status["plan"], 1)
        return {
            **status,
            "used": status["used_credits"],
            "limit": status["weekly_limit"],
            "remaining": max(0, status["weekly_limit"] - status["used_credits"]) if status["weekly_limit"] else -1,
            "project_limit": project_limit,
            "weekly_credit_limit": status["weekly_limit"],
        }

    @app.get("/api/membership")
    async def api_membership(current_user: CurrentUser = Depends(get_current_user)):
        if _is_developer_account(current_user):
            return {"plan": "developer", "status": "active", "seats": [], "unlimited": True}
        service = _get_membership_service()
        return {
            **service.status(current_user.user_id, plan_override=_membership_plan_override(current_user)),
            "seats": service.seats(current_user.user_id),
            "membership_enabled": bool(_config and _config.membership_enabled),
        }

    @app.get("/api/usage")
    async def api_usage(current_user: CurrentUser = Depends(get_current_user)):
        if _is_developer_account(current_user):
            return {"plan": "developer", "unlimited": True}
        return _get_membership_service().status(
            current_user.user_id,
            plan_override=_membership_plan_override(current_user),
        )

    @app.get("/api/membership/afdian/connect")
    async def api_afdian_connect(current_user: CurrentUser = Depends(get_current_user)):
        if _config is not None and not _config.membership_enabled:
            raise HTTPException(410, "首个测试版暂未开放会员功能")
        config = _config
        if config is None or not config.afdian_client_id or not config.afdian_client_secret:
            raise HTTPException(503, "爱发电 OAuth 尚未配置")
        service = _get_membership_service()
        state = secrets.token_urlsafe(32)
        redirect_uri = config.afdian_oauth_redirect_uri or f"{config.afdian_webhook_public_url.rstrip('/')}/api/membership/afdian/oauth/callback"
        if not redirect_uri.startswith("https://"):
            raise HTTPException(503, "爱发电 OAuth 回调地址必须使用 HTTPS")
        state_info = service.create_afdian_oauth_state(current_user.user_id, state, redirect_uri)
        return {"authorize_url": AfdianClient(config).oauth_url(state, redirect_uri), **state_info}

    @app.get("/api/membership/afdian/oauth/callback")
    async def api_afdian_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
        service = _get_membership_service()
        if not state:
            return RedirectResponse("kyrozen://billing/afdian/callback?success=0&reason=missing_state")
        state_row = service.consume_afdian_oauth_state(state)
        if not state_row:
            return RedirectResponse("kyrozen://billing/afdian/callback?success=0&reason=invalid_state")
        if error or not code or _config is None:
            return RedirectResponse("kyrozen://billing/afdian/callback?success=0&reason=authorization_failed")
        try:
            account = AfdianClient(_config).exchange_code(code, state_row["redirect_uri"])
            if not account.user_id or not account.user_private_id:
                raise AfdianError("OAuth 未返回完整用户信息")
            service.bind_afdian_account(state_row["user_id"], account.user_id, account.user_private_id)
        except (AfdianError, ValueError):
            return RedirectResponse("kyrozen://billing/afdian/callback?success=0&reason=binding_failed")
        return RedirectResponse("kyrozen://billing/afdian/callback?success=1")

    @app.post("/api/membership/afdian/checkout")
    async def api_afdian_checkout(request: AfdianCheckoutRequest, current_user: CurrentUser = Depends(get_current_user)):
        if _config is not None and not _config.membership_enabled:
            raise HTTPException(410, "首个测试版暂未开放会员功能")
        if _config is None:
            raise HTTPException(503, "支付服务未配置")
        client = AfdianClient(_config)
        plan_id = client.plan_ids().get(request.plan, "")
        if not plan_id:
            raise HTTPException(503, "该会员方案尚未配置爱发电方案 ID")
        try:
            return _get_membership_service().create_afdian_checkout(current_user.user_id, request.plan, plan_id, client.checkout_url(plan_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/membership/afdian/payment-status/{checkout_id}")
    async def api_afdian_payment_status(checkout_id: str, current_user: CurrentUser = Depends(get_current_user)):
        if _config is not None and not _config.membership_enabled:
            raise HTTPException(410, "首个测试版暂未开放会员功能")
        session = _get_membership_service().afdian_checkout(current_user.user_id, checkout_id)
        if not session:
            raise HTTPException(404, "付款会话不存在")
        return session

    @app.post("/api/webhooks/afdian")
    async def api_afdian_webhook(request: Request):
        if _config is not None and not _config.membership_enabled:
            return {"ec": 200, "em": "membership disabled in beta"}
        payload = await request.json()
        order = payload.get("data", {}).get("order", payload.get("order", payload)) if isinstance(payload, dict) else {}
        service = _get_membership_service()
        trade = str(order.get("out_trade_no") or "")
        client = AfdianClient(_config) if _config else None
        def review(reason: str):
            service.add_payment_review(trade or None, reason, {"order": order})
            return {"ec": 200, "em": "ok"}
        if not trade or int(order.get("status") or 0) != 2 or client is None:
            return review("订单缺少订单号、未成功或支付服务未配置")
        plan = client.plan_for_id(str(order.get("plan_id") or ""))
        if not plan:
            return review("未知爱发电方案 ID")
        account = service._query("SELECT * FROM afdian_accounts WHERE afdian_user_id = ?", (str(order.get("user_id") or ""),))
        if not account:
            return review("爱发电用户未绑定 Kyrozen 账号")
        try:
            confirmed = client.query_order(trade)
        except AfdianError:
            return review("爱发电订单二次查询失败")
        if int(confirmed.get("status") or 0) != 2 or str(confirmed.get("plan_id")) != str(order.get("plan_id")) or str(confirmed.get("user_id")) != str(order.get("user_id")):
            return review("订单二次校验不匹配")
        if not service.record_afdian_order(confirmed, user_id=account["user_id"], plan=plan):
            return {"ec": 200, "em": "ok"}
        service.grant_afdian_order(confirmed, user_id=account["user_id"], plan=plan)
        return {"ec": 200, "em": "ok"}

    @app.get("/api/admin/membership-payments")
    async def api_admin_membership_payments(admin: CurrentUser = Depends(require_admin)):
        service = _get_membership_service()
        return {"orders": service._query("SELECT * FROM afdian_orders ORDER BY created_at DESC", all_rows=True) or [], "reviews": service._query("SELECT * FROM membership_payment_reviews ORDER BY created_at DESC", all_rows=True) or []}

    @app.post("/api/admin/membership-payments/{order_id}/review")
    async def api_admin_review_payment(order_id: str, request: MembershipPaymentReviewRequest, admin: CurrentUser = Depends(require_admin)):
        service = _get_membership_service()
        resolved_at = datetime.now(timezone.utc).isoformat()
        if service._is_supabase:
            service.db.client.table("membership_payment_reviews").update({"status": request.status, "reason": request.reason, "resolved_at": resolved_at, "resolved_by": admin.user_id}).eq("id", order_id).execute()
        else:
            service._execute("UPDATE membership_payment_reviews SET status = ?, reason = ?, resolved_at = ?, resolved_by = ? WHERE id = ?", (request.status, request.reason, resolved_at, admin.user_id, order_id))
        return {"status": request.status, "id": order_id}

    @app.post("/api/membership/seats")
    async def api_add_membership_seat(
        request: MembershipSeatRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        if _config is not None and not _config.membership_enabled:
            raise HTTPException(410, "首个测试版暂未开放会员功能")
        if _is_developer_account(current_user):
            raise HTTPException(400, "开发者账户不需要家庭成员")
        try:
            return _get_membership_service().add_seat(current_user.user_id, request.user_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/membership/seats/{member_user_id}")
    async def api_remove_membership_seat(
        member_user_id: str,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        if _config is not None and not _config.membership_enabled:
            raise HTTPException(410, "首个测试版暂未开放会员功能")
        if not _get_membership_service().remove_seat(current_user.user_id, member_user_id):
            raise HTTPException(404, "家庭成员不存在")
        return {"status": "removed", "user_id": member_user_id}

    @app.post("/api/admin/memberships/{user_id}")
    async def api_set_membership_plan(
        user_id: str,
        request: MembershipPlanRequest,
        admin: CurrentUser = Depends(require_admin),
    ):
        if _config is not None and not _config.membership_enabled and not _is_developer_account(admin):
            raise HTTPException(410, "首个测试版暂未开放会员功能")
        try:
            return _get_membership_service().set_plan(user_id, request.plan)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/desktop/pairing-code")
    async def api_create_pairing_code():
        """Desktop client requests a pairing code to display to the user."""
        code = DesktopPairingManager.create_code()
        return {
            "code": code,
            "expires_in": 600,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat(),
        }

    @app.post("/api/desktop/poll-pairing")
    async def api_poll_pairing(request: DesktopPollPairingRequest):
        """Desktop client polls for pairing confirmation."""
        result = DesktopPairingManager.poll_code(request.code)
        if result is None:
            raise HTTPException(404, "Pairing code not found or expired")
        if result.get("pending"):
            return {"ready": False}
        return {
            "ready": True,
            "ws_token": result["ws_token"],
            "access_token": result.get("access_token"),
            "user_id": result["user_id"],
        }

    @app.post("/api/auth/confirm-pairing")
    async def api_confirm_pairing(
        request: DesktopConfirmPairingRequest,
        current_user: CurrentUser = Depends(get_current_user),
    ):
        """Browser session confirms a desktop pairing code."""
        success = DesktopPairingManager.confirm_code(
            request.code,
            current_user.user_id,
            current_user.access_token,
        )
        if not success:
            raise HTTPException(400, "Invalid or expired pairing code")
        return {"success": True}

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
                            if task.status == "pending":
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
                            if status in {"completed", "completed_with_limit", "failed", "cancelled"}:
                                task.update_status(status)
                            _db.save_task(task)
                            if (
                                status == "completed"
                                and task.project_id
                                and isinstance(result, dict)
                                and str(result.get("answer", "")).strip()
                            ):
                                # CRITICAL: persist the assistant reply to chat history so
                                # it survives app restarts. A failure here must NEVER kill
                                # the websocket loop (a previous NameError silently dropped
                                # every desktop assistant message).
                                try:
                                    _get_project_manager().save_chat_message(
                                        {
                                            "id": str(uuid.uuid4()),
                                            "user_id": user_id,
                                            "project_id": task.project_id,
                                            "role": "assistant",
                                            "content": str(result["answer"]),
                                            "metadata": {"task_id": task_id},
                                            "created_at": datetime.now(timezone.utc).isoformat(),
                                        }
                                    )
                                except Exception:
                                    logger.error(
                                        f"Failed to persist assistant chat message for task {task_id}",
                                        exc_info=True,
                                    )

                elif msg_type == "confirmation_response":
                    # TODO: wire into running agent confirmation queue
                    logger.log("info", f"Confirmation response for task {message.get('task_id')}: {message.get('confirmed')}")

                elif msg_type == "model_request":
                    asyncio.create_task(
                        _handle_model_request(
                            websocket,
                            message,
                            user_id,
                            logger,
                            developer=DesktopTokenManager.is_developer_ws_token(ws_token),
                        )
                    )

                elif msg_type == "request_pending_tasks":
                    if _db is not None:
                        for task in _db.list_tasks():
                            if not task.requires_local_client or task.status not in {
                                "pending", "running", "waiting_confirmation"
                            }:
                                continue
                            project = _db.get_project(task.project_id) if task.project_id else None
                            if project is None or project.user_id != user_id:
                                continue
                            task.assigned_client_id = client.client_id
                            _db.save_task(task)
                            await websocket.send_json({
                                "type": "assign_task",
                                "task_id": task.id,
                                "project_id": task.project_id,
                                "mode": task.mode,
                                "message": task.description,
                                "requires_confirmation": True,
                                "resumed": True,
                            })

                elif msg_type == "task_queued":
                    # The desktop has accepted ownership but is deliberately
                    # waiting for its current local task to finish.
                    logger.log(
                        "info",
                        f"Desktop queued task {message.get('task_id')} "
                        f"at position {message.get('queue_length')}",
                    )

                else:
                    logger.warning(f"Unknown desktop websocket message type: {msg_type}")

        except WebSocketDisconnect:
            logger.log("info", "Desktop client disconnected")
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
