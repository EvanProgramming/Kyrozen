"""Tests for the unified AgentRouter (Kyrozen Missing Features 3.1).

Covers:
- resolve_mode across all four signal sources (intent / requested / stage / type)
- route() building the correct specialized agent for every one of the 9 modes
- mode-based and capability-based tool restriction
- graceful degradation to a read-only BaseAgent on init failure
- structured handoff state (no re-asking of confirmed questions)
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kyrozen.config import get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.handoff import HandoffStore
from kyrozen.core.router import (
    AGENT_SPECS,
    ROUTING_MODES,
    AgentRouter,
    LocalCapabilities,
    RestrictedToolRegistry,
)
from kyrozen.tools import get_default_registry, ToolRegistry


class _FakeModel:
    """Lightweight stand-in so agents can be constructed without a real provider."""


@pytest.fixture()
def registry() -> ToolRegistry:
    return get_default_registry()


@pytest.fixture()
def base_kwargs() -> dict:
    return {"config": get_config(), "model": _FakeModel(), "memory": None}


@pytest.fixture()
def router() -> AgentRouter:
    return AgentRouter()


# --------------------------------------------------------------------------
# resolve_mode
# --------------------------------------------------------------------------


class TestResolveMode:
    def test_intent_hardware_wins(self, router: AgentRouter) -> None:
        mode, reason, signals = router.resolve_mode(
            requested_mode="development",
            user_message="帮我给 esp32 写一段固件并烧录",
        )
        assert mode == "hardware_development"
        assert any("intent" in s for s in signals)

    def test_intent_testing(self, router: AgentRouter) -> None:
        mode, _, _ = router.resolve_mode(user_message="帮我跑测试，执行单元测试")
        assert mode == "testing"

    def test_intent_learning(self, router: AgentRouter) -> None:
        mode, _, _ = router.resolve_mode(user_message="这次项目做个复盘，总结教训")
        assert mode == "learning"

    def test_requested_mode_alias(self, router: AgentRouter) -> None:
        for requested, expected in [
            ("research", "market_research"),
            ("planning", "product_definition"),
            ("hardware", "hardware_development"),
            ("solution_design", "solution_design"),
        ]:
            mode, _, _ = router.resolve_mode(requested_mode=requested)
            assert mode == expected, requested

    def test_stage_derived(self, router: AgentRouter) -> None:
        mode, _, _ = router.resolve_mode(stage="development")
        assert mode == "development"
        mode, _, _ = router.resolve_mode(stage="testing")
        assert mode == "testing"

    def test_phase2_hardware_and_protocol_stages_route_to_specialists(self, router: AgentRouter) -> None:
        assert router.resolve_mode(stage="hardware_design", project_type="embedded")[0] == "hardware_development"
        assert router.resolve_mode(stage="firmware", project_type="embedded")[0] == "hardware_development"
        assert router.resolve_mode(stage="protocol_design", project_type="hybrid")[0] == "solution_design"
        assert router.resolve_mode(stage="integration_testing", project_type="hybrid")[0] == "testing"

    def test_stage_solution_design_refines_planning(self, router: AgentRouter) -> None:
        mode, _, _ = router.resolve_mode(requested_mode="product_definition", stage="solution_design")
        assert mode == "solution_design"

    def test_fallback_to_problem_discovery(self, router: AgentRouter) -> None:
        mode, _, _ = router.resolve_mode()
        assert mode == "problem_discovery"

    def test_hardware_project_type_overrides_development(self, router: AgentRouter) -> None:
        mode, _, signals = router.resolve_mode(requested_mode="development", project_type="hardware")
        assert mode == "hardware_development"
        assert any(s.startswith("project_type:hardware") for s in signals)

    def test_hardware_project_type_overrides_iteration(self, router: AgentRouter) -> None:
        mode, _, _ = router.resolve_mode(requested_mode="iteration", project_type="hardware")
        assert mode == "hardware_development"

    def test_intent_beats_requested_mode(self, router: AgentRouter) -> None:
        # A software-dev request still routes to hardware when the message is hardware.
        mode, _, _ = router.resolve_mode(
            requested_mode="development", project_type="software", user_message="arduino 接线引脚"
        )
        assert mode == "hardware_development"

    def test_explicit_planning_dispatch_beats_hardware_text(self, router: AgentRouter) -> None:
        # The decision-center planning action sends a prompt containing ESP32
        # context. The explicit planning mode must remain authoritative.
        mode, reason, signals = router.resolve_mode(
            requested_mode="planning",
            stage="problem_discovery",
            user_message="请基于 ESP32 证据生成保守、平衡、激进三案",
        )
        assert mode == "product_definition"
        assert "requested:planning" in signals
        assert "显式派发 planning" in reason


# --------------------------------------------------------------------------
# route() — agent selection for all 9 modes
# --------------------------------------------------------------------------


class TestRouteAgentSelection:
    @pytest.mark.parametrize("mode", list(ROUTING_MODES))
    def test_all_nine_modes_build_correct_agent(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict, mode: str
    ) -> None:
        agent, effective_registry, decision = router.route(
            requested_mode=mode,
            registry=registry,
            agent_kwargs=base_kwargs,
            task_id=f"task-{mode}",
        )
        expected_class = AGENT_SPECS[mode][1]
        assert type(agent).__name__ == expected_class, mode
        assert decision.mode == mode
        assert decision.agent_name == expected_class
        assert decision.agent_display_name == AGENT_SPECS[mode][2]
        # Every decision must record the four required fields.
        assert decision.reason
        assert isinstance(decision.available_tools, list)
        assert isinstance(decision.restricted_tools, list)
        assert not decision.degraded

    def test_development_records_software_agent(self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict) -> None:
        agent, _, decision = router.route(
            requested_mode="development", registry=registry, agent_kwargs=base_kwargs
        )
        assert type(agent).__name__ == "SoftwareDevelopmentAgent"
        assert "软件开发" in decision.agent_display_name

    def test_iteration_uses_software_agent(self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict) -> None:
        agent, _, _ = router.route(requested_mode="iteration", registry=registry, agent_kwargs=base_kwargs)
        assert type(agent).__name__ == "SoftwareDevelopmentAgent"

    def test_hardware_development_agent(self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict) -> None:
        agent, _, _ = router.route(
            requested_mode="development", project_type="hardware", registry=registry, agent_kwargs=base_kwargs
        )
        assert type(agent).__name__ == "HardwareDevelopmentAgent"


# --------------------------------------------------------------------------
# tool restriction
# --------------------------------------------------------------------------


class TestToolRestriction:
    def test_conversational_modes_restrict_execution_tools(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict
    ) -> None:
        for mode in ("problem_discovery", "market_research", "product_definition", "solution_design", "learning"):
            agent, _, decision = router.route(
                requested_mode=mode, registry=registry, agent_kwargs=base_kwargs
            )
            for blocked in ("terminal", "git", "file_write", "hardware_bridge"):
                assert blocked not in decision.available_tools, (mode, blocked)
            # And the restricted tools are explicitly recorded.
            assert "terminal" in decision.restricted_tools, mode
            # The effective registry must refuse the blocked tool.
            assert isinstance(agent.tools, RestrictedToolRegistry)
            res = agent.tools.execute("terminal", "execute", {"command": "echo hi"})
            assert res.success is False

    def test_development_restricts_hardware_bridge_only(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict
    ) -> None:
        agent, _, decision = router.route(
            requested_mode="development", registry=registry, agent_kwargs=base_kwargs
        )
        assert "hardware_bridge" not in decision.available_tools
        assert "terminal" in decision.available_tools  # software dev may run commands
        assert "git" in decision.available_tools

    def test_capability_no_git_restricts_git(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict
    ) -> None:
        caps = LocalCapabilities(git=False, hardware_toolchain=True, network=True)
        _, _, decision = router.route(
            requested_mode="development", capabilities=caps, registry=registry, agent_kwargs=base_kwargs
        )
        assert "git" in decision.restricted_tools

    def test_capability_no_hardware_toolchain_restricts_hardware_bridge(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict
    ) -> None:
        caps = LocalCapabilities(git=True, hardware_toolchain=False, network=True)
        _, _, decision = router.route(
            requested_mode="testing", capabilities=caps, registry=registry, agent_kwargs=base_kwargs
        )
        assert "hardware_bridge" in decision.restricted_tools

    def test_full_capabilities_no_extra_restriction(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict
    ) -> None:
        caps = LocalCapabilities(git=True, hardware_toolchain=True, network=True)
        _, _, decision = router.route(
            requested_mode="hardware_development", capabilities=caps, registry=registry, agent_kwargs=base_kwargs
        )
        # hardware dev has no base restrictions and the toolchain is present.
        assert "hardware_bridge" not in decision.restricted_tools
        assert "git" not in decision.restricted_tools


# --------------------------------------------------------------------------
# degradation
# --------------------------------------------------------------------------


class TestDegradation:
    def test_init_failure_degrades_to_read_only_base_agent(
        self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict
    ) -> None:
        def _raise(*args, **kwargs):
            raise RuntimeError("simulated agent import/init failure")

        with patch("importlib.import_module", side_effect=_raise):
            agent, effective_registry, decision = router.route(
                requested_mode="development", registry=registry, agent_kwargs=base_kwargs
            )
        assert type(agent).__name__ == "BaseAgent"
        assert decision.degraded is True
        assert decision.agent_name == "BaseAgent"
        assert "只读" in decision.agent_display_name
        assert decision.repair_steps
        assert isinstance(effective_registry, RestrictedToolRegistry)
        # Read-only: write/execute tools are blocked, read tools allowed.
        res = effective_registry.execute("file_write", "write", {"path": "x", "content": "y"})
        assert res.success is False
        res = effective_registry.execute("file_read", "read", {"path": "x"})
        # file_read is in READ_ONLY_ALLOWED_TOOLS; the inner registry call is allowed
        # (it may still fail for a missing file, but it must not be blocked by the wrapper).
        assert "not available" not in (res.error or "")

    def test_degradation_reason_records_failure(self, router: AgentRouter, registry: ToolRegistry, base_kwargs: dict) -> None:
        def _raise(*args, **kwargs):
            raise ImportError("module kyrozen.development.agent not found")

        with patch("importlib.import_module", side_effect=_raise):
            _, _, decision = router.route(
                requested_mode="development", registry=registry, agent_kwargs=base_kwargs
            )
        assert decision.degraded_reason
        assert "ImportError" in decision.degraded_reason


# --------------------------------------------------------------------------
# structured handoff
# --------------------------------------------------------------------------


class TestHandoff:
    def test_confirmed_goal_recorded_and_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStore(Path(tmp) / "handoff.json", project_id="p1")
            assert store.add_confirmed_goal("做一个本地优先的笔记应用") is True
            assert store.add_confirmed_goal("做一个本地优先的笔记应用") is False  # duplicate
            assert len(store.confirmed_goals) == 1

    def test_context_block_renders_confirmed_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStore(Path(tmp) / "handoff.json", project_id="p1")
            store.add_confirmed_goal("目标 A")
            store.add_non_goal("不做 B")
            store.add_decision("采用 SQLite")
            block = store.context_block()
            assert "目标 A" in block
            assert "不做 B" in block
            assert "采用 SQLite" in block
            assert "请勿重复询问" in block

    def test_empty_store_has_no_context_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStore(Path(tmp) / "handoff.json", project_id="p1")
            assert store.context_block() == ""

    def test_record_handoff_snapshots_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStore(Path(tmp) / "handoff.json", project_id="p1")
            store.add_confirmed_goal("目标 A")
            store.set_current_agent("development", "SoftwareDevelopmentAgent")
            summary = store.record_handoff(
                source_mode="development",
                source_agent="SoftwareDevelopmentAgent",
                target_mode="testing",
                target_agent="TestingAgent",
            )
            assert summary["source_mode"] == "development"
            assert summary["target_mode"] == "testing"
            assert "目标 A" in summary["confirmed_goals"]
            # record_handoff snapshots state but does NOT mutate the active
            # agent; the runtime updates it afterwards via set_current_agent.
            assert store.last_mode == "development"
            store.set_current_agent("testing", "TestingAgent")
            assert store.last_mode == "testing"
            assert store.last_agent == "TestingAgent"
            # handoffs persist across reload
            reloaded = HandoffStore(Path(tmp) / "handoff.json", project_id="p1")
            assert reloaded.handoffs[0]["target_agent"] == "TestingAgent"
            assert reloaded.last_mode == "testing"


if __name__ == "__main__":
    unittest.main()
