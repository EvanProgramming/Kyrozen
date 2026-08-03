"""Unified agent routing for Kyrozen.

``AgentRouter`` is the single place that decides which specialized agent
handles a task, based on four signals:

1. project stage (server-side lifecycle stage)
2. project type (software / hardware / hybrid)
3. user intent (keyword signals in the latest message)
4. local capabilities (hardware toolchain, git, network)

Every routing decision records the chosen agent, the reason, the available
tools, and the restricted tools. If a specialized agent fails to initialize,
the router degrades to a read-only fallback agent and reports repair steps —
it never silently falls back to unrestricted generic execution.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kyrozen.core.agent import BaseAgent
from kyrozen.tools import ToolRegistry, ToolResult

# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

#: The nine canonical routing modes (问题探索、市场调研、产品定义、方案设计、
#: 软件开发、硬件开发、测试验证、迭代改进、学习复盘).
ROUTING_MODES: tuple[str, ...] = (
    "problem_discovery",
    "market_research",
    "product_definition",
    "solution_design",
    "development",
    "hardware_development",
    "testing",
    "iteration",
    "learning",
)

MODE_LABELS: dict[str, str] = {
    "problem_discovery": "问题探索",
    "market_research": "市场调研",
    "product_definition": "产品定义",
    "solution_design": "方案设计",
    "development": "软件开发",
    "hardware_development": "硬件开发",
    "testing": "测试验证",
    "iteration": "迭代改进",
    "learning": "学习复盘",
}

#: Aliases accepted from the server / older clients.
MODE_ALIASES: dict[str, str] = {
    "discovery": "problem_discovery",
    "problem_discovery": "problem_discovery",
    "market_research": "market_research",
    "research": "market_research",
    "planning": "product_definition",
    "product_definition": "product_definition",
    "solution_design": "solution_design",
    "protocol_design": "solution_design",
    "development": "development",
    "hardware_design": "hardware_development",
    "procurement": "hardware_development",
    "maker": "hardware_development",
    "firmware": "hardware_development",
    "hardware_testing": "hardware_development",
    "integration_testing": "testing",
    "hardware": "hardware_development",
    "hardware_development": "hardware_development",
    "testing": "testing",
    "iteration": "iteration",
    "learning": "learning",
}

#: Server lifecycle stage -> canonical mode.
STAGE_TO_MODE: dict[str, str] = {
    "problem_discovery": "problem_discovery",
    "market_research": "market_research",
    "product_definition": "product_definition",
    "solution_design": "solution_design",
    "protocol_design": "solution_design",
    "development": "development",
    "hardware_design": "hardware_development",
    "procurement": "hardware_development",
    "maker": "hardware_development",
    "firmware": "hardware_development",
    "hardware_testing": "hardware_development",
    "integration_testing": "testing",
    "testing": "testing",
    "iteration": "iteration",
}

#: Intent keyword patterns, checked against the user's latest message.
#: Order matters: the first match wins.
INTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "hardware_development",
        re.compile(
            r"arduino|esp32|esp8266|stm32|raspberry|platformio|\bpio\b|单片机|开发板|固件|"
            r"烧录|接线|引脚|串口|电路|传感器|pcb|电压|电流|焊接",
            re.IGNORECASE,
        ),
    ),
    (
        "testing",
        re.compile(
            r"跑测试|运行测试|执行测试|测试用例|测试计划|验收测试|回归测试|单元测试|"
            r"run tests?|test case|test plan|regression",
            re.IGNORECASE,
        ),
    ),
    (
        "learning",
        re.compile(r"复盘|总结经验|学到了|经验教训|retrospective|lessons? learned", re.IGNORECASE),
    ),
)

#: Tools each mode is NOT allowed to use. Conversational/analytical modes do
#: not execute commands, mutate files, or drive hardware.
_CONVERSATIONAL_RESTRICTED = frozenset({"terminal", "git", "file_write", "hardware_bridge"})
MODE_RESTRICTED_TOOLS: dict[str, frozenset[str]] = {
    "problem_discovery": _CONVERSATIONAL_RESTRICTED,
    "market_research": _CONVERSATIONAL_RESTRICTED,
    "product_definition": _CONVERSATIONAL_RESTRICTED,
    "solution_design": _CONVERSATIONAL_RESTRICTED,
    "development": frozenset({"hardware_bridge"}),
    "hardware_development": frozenset(),
    "testing": frozenset(),
    "iteration": frozenset(),
    "learning": _CONVERSATIONAL_RESTRICTED,
}

#: Tools that a degraded (read-only) agent may still use.
READ_ONLY_ALLOWED_TOOLS = frozenset(
    {"file_read", "list_dir", "find_files", "web_search", "search_github", "search_papers", "handoff"}
)


# --------------------------------------------------------------------------
# Capabilities
# --------------------------------------------------------------------------


@dataclass
class LocalCapabilities:
    """What the local machine can actually do."""

    hardware_toolchain: bool = False
    git: bool = False
    network: bool = True

    @classmethod
    def detect(cls) -> "LocalCapabilities":
        return cls(
            hardware_toolchain=bool(shutil.which("arduino-cli") or shutil.which("pio")),
            git=bool(shutil.which("git")),
            network=True,
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "hardware_toolchain": self.hardware_toolchain,
            "git": self.git,
            "network": self.network,
        }


# --------------------------------------------------------------------------
# Decision record
# --------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """A persisted record of one routing decision."""

    mode: str
    agent_name: str
    agent_display_name: str
    reason: str
    available_tools: list[str] = field(default_factory=list)
    restricted_tools: list[str] = field(default_factory=list)
    stage: str = ""
    project_type: str = ""
    intent_signals: list[str] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    degraded: bool = False
    degraded_reason: str = ""
    repair_steps: list[str] = field(default_factory=list)
    task_id: str = ""
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "mode_label": MODE_LABELS.get(self.mode, self.mode),
            "agent_name": self.agent_name,
            "agent_display_name": self.agent_display_name,
            "reason": self.reason,
            "available_tools": self.available_tools,
            "restricted_tools": self.restricted_tools,
            "stage": self.stage,
            "project_type": self.project_type,
            "intent_signals": self.intent_signals,
            "capabilities": self.capabilities,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "repair_steps": self.repair_steps,
            "task_id": self.task_id,
            "created_at": self.created_at,
        }


# --------------------------------------------------------------------------
# Restricted registry
# --------------------------------------------------------------------------


class RestrictedToolRegistry(ToolRegistry):
    """Wraps a ToolRegistry and hides/blocks a set of tool names.

    Blocked tools are removed from the schema list (so the model never sees
    them) and refuse execution with an explanatory error (defense in depth).
    """

    def __init__(self, inner: ToolRegistry, restricted: set[str] | frozenset[str], block_reason: str) -> None:
        super().__init__()
        self._inner = inner
        self._restricted = set(restricted)
        self._block_reason = block_reason

    def register(self, tool: Any) -> None:  # pragma: no cover - passthrough
        self._inner.register(tool)

    def get(self, name: str) -> Any:
        if name in self._restricted:
            return None
        return self._inner.get(name)

    def list_tools(self) -> list[str]:
        return [name for name in self._inner.list_tools() if name not in self._restricted]

    def list_schemas(self) -> list[dict[str, Any]]:
        return [schema for schema in self._inner.list_schemas() if schema.get("name") not in self._restricted]

    def execute(self, name: str, action: str, parameters: dict[str, Any]) -> ToolResult:
        if name in self._restricted:
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool '{name}' is not available: {self._block_reason}",
            )
        return self._inner.execute(name, action, parameters)


def build_read_only_registry(inner: ToolRegistry, reason: str) -> RestrictedToolRegistry:
    """Restrict a registry to read-only tools (degraded mode)."""
    restricted = {name for name in inner.list_tools() if name not in READ_ONLY_ALLOWED_TOOLS}
    return RestrictedToolRegistry(inner, restricted, reason)


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

#: mode -> (module path, class name, display name). Imported lazily so a
#: broken specialized module degrades gracefully instead of crashing startup.
AGENT_SPECS: dict[str, tuple[str, str, str]] = {
    "problem_discovery": ("kyrozen.discovery.agent", "ProblemDiscoveryAgent", "问题探索 Agent"),
    "market_research": ("kyrozen.research.agent", "MarketResearchAgent", "市场调研 Agent"),
    "product_definition": ("kyrozen.planning.agent", "ProductPlanningAgent", "产品定义 Agent"),
    "solution_design": ("kyrozen.planning.agent", "ProductPlanningAgent", "方案设计 Agent"),
    "development": ("kyrozen.development.agent", "SoftwareDevelopmentAgent", "软件开发 Agent"),
    "hardware_development": ("kyrozen.hardware.agent", "HardwareDevelopmentAgent", "硬件开发 Agent"),
    "testing": ("kyrozen.testing.agent", "TestingAgent", "测试验证 Agent"),
    "iteration": ("kyrozen.development.agent", "SoftwareDevelopmentAgent", "迭代改进 Agent"),
    "learning": ("kyrozen.learning.agent", "LearningAgent", "学习复盘 Agent"),
}

DEFAULT_REPAIR_STEPS: list[str] = [
    "在设置页检查 Python 运行环境状态，必要时点击「修复运行环境」重新安装。",
    "重启 Kyrozen 桌面客户端以重新初始化本地 Agent。",
    "确认应用未被安全软件拦截，且磁盘剩余空间充足。",
    "若问题持续，请在设置页导出诊断日志并联系支持。",
]


class AgentRouter:
    """The single router that maps a task to a specialized agent."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.log_path = Path(log_path) if log_path else None
        self.last_decision: RoutingDecision | None = None

    # ------------------------------------------------------------- resolve

    def resolve_mode(
        self,
        *,
        requested_mode: str = "",
        stage: str = "",
        project_type: str = "",
        user_message: str = "",
    ) -> tuple[str, str, list[str]]:
        """Return (mode, reason, intent_signals)."""
        signals: list[str] = []
        reasons: list[str] = []

        # 1. Explicit user intent in the latest message wins.
        intent_mode = ""
        for mode_name, pattern in INTENT_PATTERNS:
            match = pattern.search(user_message or "")
            if match:
                intent_mode = mode_name
                signals.append(f"intent:{match.group(0).lower()}")
                break

        # 2. Requested mode (server dispatch), normalized through aliases.
        alias_mode = MODE_ALIASES.get((requested_mode or "").strip().lower(), "")

        # 3. Stage-derived mode.
        stage_mode = STAGE_TO_MODE.get((stage or "").strip().lower(), "")

        mode = intent_mode or alias_mode or stage_mode or "problem_discovery"
        if intent_mode:
            reasons.append(f"用户消息包含{MODE_LABELS[intent_mode]}意图信号（{signals[0].split(':', 1)[1]}）")
        elif alias_mode:
            reasons.append(f"云端派发模式 {requested_mode} → {MODE_LABELS[alias_mode]}")
        elif stage_mode:
            reasons.append(f"项目阶段 {stage} → {MODE_LABELS[stage_mode]}")
        else:
            reasons.append("缺少阶段与模式信息，回退到问题探索")

        # planning 阶段细分：solution_design 阶段用方案设计语义。
        if mode == "product_definition" and (stage or "").strip().lower() == "solution_design":
            mode = "solution_design"
            reasons.append("阶段为 solution_design，细化为方案设计")

        # 4. Project type adjusts execution modes.
        ptype = (project_type or "").strip().lower()
        if ptype == "hardware":
            if mode == "development":
                mode = "hardware_development"
                reasons.append("硬件项目的开发任务由硬件开发 Agent 处理")
            elif mode == "iteration":
                mode = "hardware_development"
                reasons.append("硬件项目的迭代改进由硬件开发 Agent 处理")
        if ptype:
            signals.append(f"project_type:{ptype}")

        return mode, "；".join(reasons), signals

    # -------------------------------------------------------------- create

    def route(
        self,
        *,
        requested_mode: str = "",
        stage: str = "",
        project_type: str = "",
        user_message: str = "",
        capabilities: LocalCapabilities | None = None,
        registry: ToolRegistry,
        agent_kwargs: dict[str, Any] | None = None,
        task_id: str = "",
    ) -> tuple[BaseAgent, ToolRegistry, RoutingDecision]:
        """Resolve the mode, build the agent, and record the decision.

        Returns ``(agent, effective_registry, decision)``. On specialized
        agent initialization failure the returned agent is a read-only
        ``BaseAgent`` and ``decision.degraded`` is ``True``.
        """
        capabilities = capabilities or LocalCapabilities.detect()
        agent_kwargs = dict(agent_kwargs or {})

        mode, reason, signals = self.resolve_mode(
            requested_mode=requested_mode,
            stage=stage,
            project_type=project_type,
            user_message=user_message,
        )

        module_path, class_name, display_name = AGENT_SPECS[mode]

        # Mode restrictions + capability restrictions.
        restricted: set[str] = set(MODE_RESTRICTED_TOOLS.get(mode, frozenset()))
        capability_notes: list[str] = []
        if not capabilities.hardware_toolchain and "hardware_bridge" not in restricted:
            restricted.add("hardware_bridge")
            capability_notes.append("本机未检测到硬件工具链（arduino-cli / pio），硬件桥接工具已受限")
        if not capabilities.git and "git" not in restricted:
            restricted.add("git")
            capability_notes.append("本机未检测到 git，Git 工具已受限")
        if capability_notes:
            reason = reason + "；" + "；".join(capability_notes)

        all_tools = registry.list_tools()
        effective_restricted = sorted(restricted & set(all_tools))
        effective_registry: ToolRegistry = (
            RestrictedToolRegistry(registry, restricted, f"当前模式（{MODE_LABELS[mode]}）或本地能力不允许使用该工具")
            if effective_restricted
            else registry
        )

        decision = RoutingDecision(
            mode=mode,
            agent_name=class_name,
            agent_display_name=display_name,
            reason=reason,
            available_tools=[name for name in all_tools if name not in restricted],
            restricted_tools=effective_restricted,
            stage=stage,
            project_type=project_type,
            intent_signals=signals,
            capabilities=capabilities.to_dict(),
            task_id=task_id,
        )

        try:
            import importlib

            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            agent: BaseAgent = agent_class(tools=effective_registry, **agent_kwargs)
            # Let the agent know which routed mode it is serving (one agent class
            # can serve multiple modes, e.g. ProductPlanningAgent handles both
            # product_definition and solution_design with different mandates).
            agent.route_mode = mode
        except Exception as exc:  # noqa: BLE001 - any init failure must degrade, not crash
            read_only = build_read_only_registry(
                registry,
                "本地专用 Agent 初始化失败，当前处于只读模式，禁止修改文件或执行命令",
            )
            decision.degraded = True
            decision.degraded_reason = f"{display_name}（{class_name}）初始化失败：{type(exc).__name__}: {exc}"
            decision.repair_steps = list(DEFAULT_REPAIR_STEPS)
            decision.agent_name = "BaseAgent"
            decision.agent_display_name = f"{display_name}（只读降级）"
            decision.available_tools = read_only.list_tools()
            decision.restricted_tools = sorted(set(registry.list_tools()) - set(read_only.list_tools()))
            decision.reason += "；专用 Agent 初始化失败，降级为只读模式"
            agent = BaseAgent(tools=read_only, **agent_kwargs)
            effective_registry = read_only

        self.last_decision = decision
        self._persist(decision)
        return agent, effective_registry, decision

    # ------------------------------------------------------------- persist

    def _persist(self, decision: RoutingDecision) -> None:
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass  # routing must never fail because the log is unwritable
