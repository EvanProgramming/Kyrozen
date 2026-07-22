"""Tests for Kyrozen Phase 8 Testing, Validation and Iteration Loop."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.planning.models import PRD, MVP
from kyrozen.project.context import ProjectContextBuilder
from kyrozen.testing.models import (
    IterationItem,
    IterationPlan,
    TestCase,
    TestPlan,
    TestResult,
    TestingArtifactBundle,
    UserFeedback,
    ValidationReport,
)
from kyrozen.testing.state import TestingSession, VALID_TESTING_STAGES
from kyrozen.tools.testing_tools import (
    RecordUserFeedbackTool,
    RunHardwareTestTool,
    RunSoftwareTestTool,
    SaveIterationPlanTool,
    SaveTestCaseTool,
    SaveTestPlanTool,
    SaveTestResultTool,
    SaveValidationReportTool,
)

# Pytest should not treat these dataclasses as test classes.
TestCase.__test__ = False
TestResult.__test__ = False
TestPlan.__test__ = False

from tests.conftest import MockModel, make_authenticated_app


@pytest.fixture
def test_plan_data() -> dict[str, Any]:
    return {
        "name": "MVP Validation Plan",
        "objective": "Verify the MVP solves the user's core problem",
        "requirements": [
            "Users can view real-time device status",
            "Users receive low-battery alerts",
        ],
        "test_cases": [
            {
                "id": "TC-SW-01",
                "name": "Status page renders",
                "type": "ui",
                "related_requirement": "Users can view real-time device status",
                "related_feature": "Status Dashboard",
                "description": "Open the status page and check data is visible",
                "steps": ["Open /status", "Wait for data"],
                "expected": "Status values are displayed",
                "environment": "Chrome / local server",
                "priority": "high",
                "status": "ready",
            }
        ],
        "success_criteria": "All high-priority tests pass and user feedback is positive",
        "environment": "Local development environment",
        "status": "ready",
    }


@pytest.fixture
def test_case_data() -> dict[str, Any]:
    return {
        "id": "TC-SW-02",
        "name": "API returns status JSON",
        "type": "api",
        "related_requirement": "Users can view real-time device status",
        "related_feature": "Status API",
        "description": "Call the status endpoint",
        "steps": ["GET /api/status"],
        "expected": "200 OK with JSON body",
        "environment": "local",
        "priority": "high",
        "status": "ready",
    }


@pytest.fixture
def test_result_data() -> dict[str, Any]:
    return {
        "test_case_id": "TC-SW-01",
        "test_case_name": "Status page renders",
        "result": "passed",
        "actual": "Page loaded and values visible",
        "errors": "",
        "stdout": "pytest output",
        "stderr": "",
        "timestamp": "2026-07-22T10:00:00+00:00",
        "duration_ms": 1200,
        "environment": "Chrome / local server",
        "executed_by": "agent",
    }


@pytest.fixture
def user_feedback_data() -> dict[str, Any]:
    return {
        "source_type": "trial",
        "content": "I could see the status but the steps to connect were confusing.",
        "problems": [" onboarding is unclear"],
        "sentiment": "negative",
        "timestamp": "2026-07-22T11:00:00+00:00",
        "participant_id": "U1",
    }


@pytest.fixture
def validation_report_data() -> dict[str, Any]:
    return {
        "original_problem": "Users don't know device status without physically checking it",
        "tested_solution": "Web status dashboard",
        "test_results_summary": {"passed": 3, "failed": 1},
        "user_feedback": [
            {
                "source_type": "survey",
                "content": "Useful but too many steps",
                "problems": ["complex setup"],
                "sentiment": "neutral",
                "timestamp": "2026-07-22T11:00:00+00:00",
                "participant_id": "U2",
            }
        ],
        "success_metrics": "80% of users can view status within 30 seconds",
        "conclusion": "partial",
        "next_iteration": [
            {
                "category": "modify",
                "target": "Reduce first-time setup steps",
                "reason": "User feedback indicates setup is too complex",
                "priority": "high",
            }
        ],
    }


@pytest.fixture
def iteration_plan_data() -> dict[str, Any]:
    return {
        "items": [
            {
                "category": "keep",
                "target": "Real-time status display",
                "reason": "Users found it valuable",
                "priority": "high",
            },
            {
                "category": "modify",
                "target": "First-time setup flow",
                "reason": "Users reported confusion",
                "priority": "high",
            },
            {
                "category": "investigate",
                "target": "Mobile browser compatibility",
                "reason": "Not tested yet",
                "priority": "medium",
            },
        ],
        "overall_recommendation": "Improve onboarding before adding new features",
    }


def test_test_plan_serialization(test_plan_data: dict[str, Any]):
    plan = TestPlan.from_dict(test_plan_data)
    assert plan.name == "MVP Validation Plan"
    assert len(plan.test_cases) == 1
    assert plan.test_cases[0].id == "TC-SW-01"
    data = plan.to_dict()
    assert data["success_criteria"] == "All high-priority tests pass and user feedback is positive"
    restored = TestPlan.from_dict(data)
    assert restored.status == "ready"


def test_test_plan_invalid_status():
    with pytest.raises(ValueError):
        TestPlan(status="archived")


def test_test_case_invalid_type():
    with pytest.raises(ValueError):
        TestCase(type="load_test")


def test_test_case_invalid_priority():
    with pytest.raises(ValueError):
        TestCase(priority="urgent")


def test_test_result_serialization(test_result_data: dict[str, Any]):
    result = TestResult.from_dict(test_result_data)
    assert result.result == "passed"
    assert result.duration_ms == 1200
    data = result.to_dict()
    assert TestResult.from_dict(data).test_case_name == "Status page renders"


def test_test_result_invalid_result():
    with pytest.raises(ValueError):
        TestResult(result="broken")


def test_user_feedback_serialization(user_feedback_data: dict[str, Any]):
    fb = UserFeedback.from_dict(user_feedback_data)
    assert fb.source_type == "trial"
    assert fb.sentiment == "negative"
    assert fb.problems == [" onboarding is unclear"]
    data = fb.to_dict()
    assert UserFeedback.from_dict(data).participant_id == "U1"


def test_user_feedback_invalid_source():
    with pytest.raises(ValueError):
        UserFeedback(source_type="review")


def test_iteration_item_serialization():
    item = IterationItem(category="remove", target="GPS", reason="Not core need", priority="medium")
    data = item.to_dict()
    restored = IterationItem.from_dict(data)
    assert restored.category == "remove"
    assert restored.priority == "medium"


def test_iteration_item_invalid_category():
    with pytest.raises(ValueError):
        IterationItem(category="deprecated")


def test_validation_report_serialization(validation_report_data: dict[str, Any]):
    report = ValidationReport.from_dict(validation_report_data)
    assert report.conclusion == "partial"
    assert len(report.user_feedback) == 1
    assert len(report.next_iteration) == 1
    data = report.to_dict()
    restored = ValidationReport.from_dict(data)
    assert restored.original_problem == validation_report_data["original_problem"]


def test_validation_report_invalid_conclusion():
    with pytest.raises(ValueError):
        ValidationReport(conclusion="maybe")


def test_testing_artifact_bundle_round_trip(
    test_plan_data: dict[str, Any],
    test_result_data: dict[str, Any],
    validation_report_data: dict[str, Any],
    iteration_plan_data: dict[str, Any],
    user_feedback_data: dict[str, Any],
):
    bundle = TestingArtifactBundle(
        test_plan=TestPlan.from_dict(test_plan_data),
        test_results=[TestResult.from_dict(test_result_data)],
        validation_report=ValidationReport.from_dict(validation_report_data),
        iteration_plan=IterationPlan.from_dict(iteration_plan_data),
        user_feedback=[UserFeedback.from_dict(user_feedback_data)],
    )
    data = bundle.to_dict()
    restored = TestingArtifactBundle.from_dict(data)
    assert restored.test_plan.name == "MVP Validation Plan"
    assert len(restored.test_results) == 1
    assert restored.validation_report.conclusion == "partial"
    assert len(restored.iteration_plan.items) == 3
    assert restored.user_feedback[0].sentiment == "negative"


def test_testing_session_state():
    session = TestingSession(project_id="proj_test")
    assert session.stage == "understanding_inputs"
    session.set_stage("planning")
    assert session.stage == "planning"
    assert "Stage: planning" in session.logs

    plan = TestPlan(name="Plan A")
    session.update_test_plan(plan)
    assert session.test_plan.name == "Plan A"

    case = TestCase(name="Check UI", type="ui")
    session.add_or_update_test_case(case)
    assert len(session.test_plan.test_cases) == 1
    assert session.test_plan.test_cases[0].id.startswith("TC-")

    case2 = TestCase(id=session.test_plan.test_cases[0].id, name="Check UI v2", type="ui")
    session.add_or_update_test_case(case2)
    assert len(session.test_plan.test_cases) == 1
    assert session.test_plan.test_cases[0].name == "Check UI v2"

    result = TestResult(test_case_id="TC-001", result="passed")
    session.add_test_result(result)
    assert len(session.test_results) == 1

    fb = UserFeedback(source_type="interview", sentiment="positive")
    session.add_user_feedback(fb)
    assert len(session.user_feedback) == 1

    report = ValidationReport(conclusion="pass")
    session.update_validation_report(report)
    assert session.validation_report.conclusion == "pass"

    iteration = IterationPlan(items=[IterationItem(category="keep", target="X")])
    session.update_iteration_plan(iteration)
    assert len(session.iteration_plan.items) == 1


def test_testing_session_invalid_stage():
    with pytest.raises(ValueError):
        TestingSession(project_id="proj", stage="archived")
    session = TestingSession(project_id="proj")
    with pytest.raises(ValueError):
        session.set_stage("archived")


def test_testing_session_round_trip():
    session = TestingSession(project_id="proj_y")
    session.set_stage("executing")
    session.update_test_plan(TestPlan(name="Plan Y"))
    session.add_test_result(TestResult(test_case_id="TC-001", result="failed"))
    data = session.to_dict()
    restored = TestingSession.from_dict(data)
    assert restored.project_id == "proj_y"
    assert restored.stage == "executing"
    assert restored.test_plan.name == "Plan Y"
    assert restored.test_results[0].result == "failed"


def test_valid_testing_stages_defined():
    assert "understanding_inputs" in VALID_TESTING_STAGES
    assert "planning" in VALID_TESTING_STAGES
    assert "executing" in VALID_TESTING_STAGES
    assert "collecting_feedback" in VALID_TESTING_STAGES
    assert "validating" in VALID_TESTING_STAGES
    assert "iterating" in VALID_TESTING_STAGES
    assert "completed" in VALID_TESTING_STAGES
    assert "failed" in VALID_TESTING_STAGES


def test_save_test_plan_tool(project_manager, test_plan_data: dict[str, Any]):
    tool = SaveTestPlanTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("save", {"project_id": project.id, "plan": test_plan_data})
    assert result.success, result.error
    assert "artifact_id" in result.data
    assert result.data["version"] == 1


def test_save_test_case_tool(project_manager, test_case_data: dict[str, Any]):
    tool = SaveTestCaseTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("save", {"project_id": project.id, "case": test_case_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_save_test_result_tool(project_manager, test_result_data: dict[str, Any]):
    tool = SaveTestResultTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("save", {"project_id": project.id, "result": test_result_data})
    assert result.success, result.error
    assert "artifact_id" in result.data
    # timestamp should be auto-populated if missing
    result2 = tool.execute(
        "save",
        {
            "project_id": project.id,
            "result": {
                "test_case_id": "TC-SW-03",
                "test_case_name": "No timestamp",
                "result": "passed",
            },
        },
    )
    assert result2.success, result2.error


def test_record_user_feedback_tool(project_manager, user_feedback_data: dict[str, Any]):
    tool = RecordUserFeedbackTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("record", {"project_id": project.id, "feedback": user_feedback_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_save_validation_report_tool(project_manager, validation_report_data: dict[str, Any]):
    tool = SaveValidationReportTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("save", {"project_id": project.id, "report": validation_report_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_save_iteration_plan_tool(project_manager, iteration_plan_data: dict[str, Any]):
    tool = SaveIterationPlanTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("save", {"project_id": project.id, "plan": iteration_plan_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_run_software_test_tool_runs_safe_command(project_manager):
    tool = RunSoftwareTestTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("run", {"project_id": project.id, "command": "echo hello"})
    assert result.success, result.error
    assert "hello" in result.data["stdout"]


def test_run_software_test_tool_blocks_dangerous_command(project_manager):
    tool = RunSoftwareTestTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("run", {"project_id": project.id, "command": "rm -rf /"})
    assert not result.success
    assert "blocked" in result.error.lower()


def test_run_hardware_test_tool_list_ports(project_manager):
    tool = RunHardwareTestTool(project_manager)
    project = project_manager.create(name="Test Project", goal="G")
    result = tool.execute("list_ports", {"project_id": project.id})
    # The bridge returns success=False if no hardware tool is installed, but the tool itself runs.
    assert result.data is not None
    assert "stderr" in result.data or "stdout" in result.data


def test_run_hardware_test_tool_requires_project_id():
    tool = RunHardwareTestTool(None)
    result = tool.execute("list_ports", {"project_id": "x"})
    assert not result.success
    assert "manager" in result.error.lower()


def test_testing_agent_prompt_contains_tools():
    from kyrozen.testing.agent import TestingAgent

    config = KyrozenConfig(provider="mock", api_key="test", permission_mode="permissive")
    agent = TestingAgent(config=config, model=MockModel(), project_manager=None)
    prompt = agent._build_system_prompt()
    assert "save_test_plan" in prompt
    assert "save_test_case" in prompt
    assert "save_test_result" in prompt
    assert "record_user_feedback" in prompt
    assert "save_validation_report" in prompt
    assert "save_iteration_plan" in prompt
    assert "run_software_test" in prompt
    assert "run_hardware_test" in prompt
    assert "User validation is required" in prompt
    assert "Do NOT change product requirements" in prompt


def test_build_testing_context_loads_prd(project_manager):
    from kyrozen.memory import InMemoryMemory

    builder = ProjectContextBuilder(project_manager, memory=InMemoryMemory())
    project = project_manager.create(
        name="Testing Context", goal="Validate MVP", description="simple device dashboard"
    )

    prd = PRD(
        overview="Device dashboard",
        functional_requirements=["View real-time status", "Receive alerts"],
        non_functional_requirements=["Latency under 1s"],
        mvp_scope=MVP(mvp_features=["Status page"]),
        out_of_scope=["Mobile app"],
    )
    project_manager.save_artifact(
        project.id,
        type="prd",
        title="Product Requirements Document",
        content=json.dumps(prd.to_dict()),
        change_reason="Seed",
    )

    ctx = builder.build_testing_context(project)
    assert "[Testing & Validation Context]" in ctx
    assert "Device dashboard" in ctx
    assert "View real-time status" in ctx
    assert "Latency under 1s" in ctx
    assert "Mobile app" in ctx


@pytest.fixture
def api_client(temp_dir: str):
    config = KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="permissive",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
    )
    app = make_authenticated_app(config, MockModel(["Done"]))
    with TestClient(app) as client:
        yield client


def _seed_prd(api_client: TestClient, project_id: str) -> None:
    prd = PRD(
        overview="A simple device dashboard",
        functional_requirements=["View real-time status", "Receive alerts"],
        non_functional_requirements=["Latency under 1s"],
        mvp_scope=MVP(mvp_features=["Status page"]),
        out_of_scope=["Mobile app"],
    )
    api_client.post(f"/api/projects/{project_id}/artifacts", json={
        "type": "prd",
        "title": "Product Requirements Document",
        "content": json.dumps(prd.to_dict()),
        "change_reason": "Seed",
    })


def test_testing_chat_mode(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Testing Project", "goal": "G"})
    pid = create.json()["id"]
    _seed_prd(api_client, pid)

    chat_res = api_client.post("/api/chat", json={
        "message": "开始测试",
        "project_id": pid,
        "mode": "testing",
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["project_id"] == pid
    assert data["mode"] == "testing"
    assert data["task_id"].startswith("task_")


def test_testing_state_endpoint(api_client: TestClient, test_plan_data: dict[str, Any]):
    create = api_client.post("/api/projects", json={"name": "Testing Project 2", "goal": "G"})
    pid = create.json()["id"]

    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_plan",
        "title": "Test Plan",
        "content": json.dumps(test_plan_data),
        "change_reason": "Seed",
    })

    result = TestResult(test_case_id="TC-SW-01", test_case_name="Status page renders", result="passed")
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_result",
        "title": "Test Result: TC-SW-01",
        "content": json.dumps(result.to_dict()),
        "change_reason": "Seed",
    })

    feedback = UserFeedback(source_type="trial", sentiment="negative", content="Too complex")
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "user_feedback",
        "title": "User Feedback: trial",
        "content": json.dumps(feedback.to_dict()),
        "change_reason": "Seed",
    })

    report = ValidationReport(
        original_problem="Hard to check device status",
        tested_solution="Web dashboard",
        conclusion="partial",
        success_metrics="80% success rate",
    )
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "validation_report",
        "title": "Validation Report",
        "content": json.dumps(report.to_dict()),
        "change_reason": "Seed",
    })

    iteration = IterationPlan(
        items=[IterationItem(category="modify", target="Setup flow", reason="User confusion", priority="high")]
    )
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "iteration_plan",
        "title": "Iteration Plan",
        "content": json.dumps(iteration.to_dict()),
        "change_reason": "Seed",
    })

    res = api_client.get(f"/api/projects/{pid}/testing/state")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    assert data["test_plan"]["name"] == "MVP Validation Plan"
    assert len(data["test_results"]) == 1
    assert data["test_results"][0]["result"] == "passed"
    assert len(data["user_feedback"]) == 1
    assert data["validation_report"]["conclusion"] == "partial"
    assert len(data["iteration_plan"]["items"]) == 1
    assert data["iteration_plan"]["items"][0]["category"] == "modify"


def test_testing_state_requires_project(api_client: TestClient):
    res = api_client.get("/api/projects/proj_missing/testing/state")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Scenario tests mapping to the three required validation cases.
# ---------------------------------------------------------------------------


def test_case_software_auto_test_bug_fix_flow(project_manager):
    """Case 1: Software project automatic test, bug record, and fix flow."""
    project = project_manager.create(name="Case 1: Status Dashboard", goal="Validate web dashboard")

    # Save a test plan derived from a requirement.
    plan = TestPlan(
        name="Status Dashboard Validation",
        objective="Verify the status page shows real-time data",
        requirements=["Users can view real-time device status"],
        test_cases=[
            TestCase(
                id="TC-SW-01",
                name="Status page renders with data",
                type="ui",
                related_requirement="Users can view real-time device status",
                related_feature="Status Dashboard",
                steps=["Open /status", "Wait 2s"],
                expected="Status visible",
                priority="high",
                status="ready",
            )
        ],
        success_criteria="Page renders and data is visible",
        environment="local server + Chrome",
    )
    plan_tool = SaveTestPlanTool(project_manager)
    assert plan_tool.execute("save", {"project_id": project.id, "plan": plan.to_dict()}).success

    # Run an automated software test command (safe echo simulating a test runner).
    run_tool = RunSoftwareTestTool(project_manager)
    run_result = run_tool.execute("run", {"project_id": project.id, "command": "echo '1 passed, 0 failed'"})
    assert run_result.success

    # Save a failing test result representing a bug.
    bug_result = TestResult(
        test_case_id="TC-SW-01",
        test_case_name="Status page renders with data",
        result="failed",
        actual="Page shows 'loading' forever",
        errors="Timeout waiting for WebSocket data",
        stdout="",
        stderr="Connection refused on ws://localhost:8080",
    )
    result_tool = SaveTestResultTool(project_manager)
    assert result_tool.execute("save", {"project_id": project.id, "result": bug_result.to_dict()}).success

    # Save an iteration item proposing the fix (not modifying code automatically).
    iteration = IterationPlan(
        items=[
            IterationItem(
                category="investigate",
                target="WebSocket connection on local server",
                reason="Test failed because status page cannot connect to WebSocket",
                priority="high",
            )
        ]
    )
    iteration_tool = SaveIterationPlanTool(project_manager)
    assert iteration_tool.execute("save", {"project_id": project.id, "plan": iteration.to_dict()}).success

    latest_result = project_manager.get_latest_artifact(project.id, "test_result", title="Test Result: TC-SW-01 -> failed")
    assert latest_result is not None
    restored = TestResult.from_dict(json.loads(latest_result.content))
    assert restored.result == "failed"
    assert "WebSocket" in restored.errors


def test_case_hardware_compile_upload_log(project_manager):
    """Case 2: Hardware project compile, upload, serial monitor and test record."""
    project = project_manager.create(name="Case 2: Sensor Node", goal="Validate sensor node firmware")

    plan = TestPlan(
        name="Sensor Node Hardware Tests",
        objective="Verify firmware compiles and basic sensor reading works",
        requirements=["Firmware compiles", "Sensor data appears on serial"],
        test_cases=[
            TestCase(
                id="TC-HW-01",
                name="Firmware compile test",
                type="hardware_compile",
                related_requirement="Firmware compiles",
                related_feature="Sensor Firmware",
                steps=["Run arduino-cli compile"],
                expected="Build succeeds",
                priority="high",
                status="ready",
            ),
            TestCase(
                id="TC-HW-02",
                name="Serial monitor logs sensor data",
                type="hardware_stability",
                related_requirement="Sensor data appears on serial",
                related_feature="Sensor Firmware",
                steps=["Upload firmware", "Open serial monitor"],
                expected="Sensor values printed every second",
                priority="high",
                status="ready",
            ),
        ],
    )
    plan_tool = SaveTestPlanTool(project_manager)
    assert plan_tool.execute("save", {"project_id": project.id, "plan": plan.to_dict()}).success

    # Attempt to list ports (safe even without hardware tools installed).
    hw_tool = RunHardwareTestTool(project_manager)
    ports_result = hw_tool.execute("list_ports", {"project_id": project.id})
    assert ports_result.data is not None

    # Record a hardware test result.
    result = TestResult(
        test_case_id="TC-HW-01",
        test_case_name="Firmware compile test",
        result="failed",
        actual="arduino-cli not installed",
        errors="Tool not found: arduino-cli",
    )
    result_tool = SaveTestResultTool(project_manager)
    assert result_tool.execute("save", {"project_id": project.id, "result": result.to_dict()}).success

    latest = project_manager.get_latest_artifact(project.id, "test_result", title="Test Result: TC-HW-01 -> failed")
    assert latest is not None
    restored = TestResult.from_dict(json.loads(latest.content))
    assert restored.result == "failed"


def test_case_user_feedback_generates_iteration(project_manager):
    """Case 3: Real user feedback leads to next-iteration recommendations."""
    project = project_manager.create(
        name="Case 3: User Validation", goal="Validate product usability"
    )

    # Record user feedback: "功能可以使用，但是操作太复杂"
    feedback = UserFeedback(
        source_type="trial",
        content="功能可以使用，但是操作太复杂",
        problems=["操作太复杂", "首次配置步骤太多"],
        sentiment="negative",
        participant_id="P1",
    )
    fb_tool = RecordUserFeedbackTool(project_manager)
    assert fb_tool.execute("record", {"project_id": project.id, "feedback": feedback.to_dict()}).success

    # Build validation report referencing the feedback.
    report = ValidationReport(
        original_problem="用户觉得现有工具操作复杂",
        tested_solution="新版 Web 仪表盘",
        conclusion="partial",
        success_metrics="用户能在 3 步内完成首次配置",
        user_feedback=[feedback],
    )
    report_tool = SaveValidationReportTool(project_manager)
    assert report_tool.execute("save", {"project_id": project.id, "report": report.to_dict()}).success

    # Generate iteration plan: reduce first-time setup steps.
    iteration = IterationPlan(
        items=[
            IterationItem(
                category="modify",
                target="首次配置流程",
                reason="用户反馈显示操作太复杂，需要减少步骤",
                priority="high",
            ),
            IterationItem(
                category="investigate",
                target="是否可以通过二维码自动填充 Wi-Fi 信息",
                reason="进一步降低首次配置负担",
                priority="medium",
            ),
        ],
        overall_recommendation="优化首次配置体验，再验证用户满意度",
    )
    iteration_tool = SaveIterationPlanTool(project_manager)
    assert iteration_tool.execute("save", {"project_id": project.id, "plan": iteration.to_dict()}).success

    latest_iteration = project_manager.get_latest_artifact(
        project.id, "iteration_plan", title="Iteration Plan"
    )
    assert latest_iteration is not None
    restored = IterationPlan.from_dict(json.loads(latest_iteration.content))
    assert any(item.category == "modify" and "首次配置" in item.target for item in restored.items)
    assert restored.overall_recommendation == "优化首次配置体验，再验证用户满意度"
