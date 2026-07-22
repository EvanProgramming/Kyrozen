"""Tests for Kyrozen Phase 6 Software Development."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.development.models import (
    DEVELOPMENT_DECISIONS,
    VALID_APPLICATION_TYPES,
    VALID_DEVELOPMENT_STAGES,
    VALID_FEATURE_STATUSES,
    DeploymentGuide,
    DevelopmentArtifactBundle,
    FeatureImplementation,
    TechnicalPlan,
    TestReport,
)
from kyrozen.development.state import DevelopmentSession
from kyrozen.planning.models import PRD, MVP, ProductBrief, ProductGoal, TargetUser

# Pytest should not treat these dataclasses as test classes.
TestReport.__test__ = False
from kyrozen.project.context import ProjectContextBuilder
from kyrozen.tools.development_tools import (
    RecordDevelopmentDecisionTool,
    SaveDeploymentGuideTool,
    SaveFeatureImplementationTool,
    SaveTechnicalPlanTool,
    SaveTestReportTool,
)

from tests.conftest import MockModel, make_authenticated_app


@pytest.fixture
def technical_plan_data() -> dict[str, Any]:
    return {
        "application_type": "web_app",
        "architecture": "Single-page frontend + lightweight backend",
        "frontend": "Vanilla HTML/JS",
        "backend": "Python Flask",
        "database": "SQLite",
        "apis": "REST JSON",
        "deployment": "Local run",
        "dependencies": ["flask"],
        "rationale": "Keep MVP simple and self-contained",
    }


@pytest.fixture
def feature_record_data() -> dict[str, Any]:
    return {
        "prd_feature": "Users can upload images",
        "files": ["frontend/upload.js", "backend/app.py"],
        "tests": ["tests/test_upload.py"],
        "status": "implemented",
        "notes": "Basic upload endpoint",
    }


@pytest.fixture
def test_report_data() -> dict[str, Any]:
    return {
        "total": 10,
        "passed": 9,
        "failed": 1,
        "skipped": 0,
        "errors": [{"test": "test_upload", "message": "timeout"}],
        "fix_history": [{"fix": "increased timeout", "test": "test_upload"}],
    }


@pytest.fixture
def deployment_guide_data() -> dict[str, Any]:
    return {
        "run_instructions": "python -m flask run",
        "deployment_instructions": "Deploy to any Python host",
        "requirements": ["flask", "pytest"],
        "environment_variables": ["FLASK_ENV"],
    }


def test_technical_plan_serialization(technical_plan_data: dict[str, Any]):
    plan = TechnicalPlan.from_dict(technical_plan_data)
    assert plan.application_type == "web_app"
    assert plan.dependencies == ["flask"]
    data = plan.to_dict()
    assert data["architecture"] == "Single-page frontend + lightweight backend"
    restored = TechnicalPlan.from_dict(data)
    assert restored.rationale == "Keep MVP simple and self-contained"


def test_technical_plan_invalid_application_type():
    with pytest.raises(ValueError):
        TechnicalPlan(application_type="microservices")


def test_feature_implementation_serialization(feature_record_data: dict[str, Any]):
    record = FeatureImplementation.from_dict(feature_record_data)
    assert record.prd_feature == "Users can upload images"
    assert "frontend/upload.js" in record.files
    assert record.status == "implemented"
    data = record.to_dict()
    assert FeatureImplementation.from_dict(data).tests == ["tests/test_upload.py"]


def test_feature_implementation_invalid_status():
    with pytest.raises(ValueError):
        FeatureImplementation(status="rejected")


def test_test_report_serialization(test_report_data: dict[str, Any]):
    report = TestReport.from_dict(test_report_data)
    assert report.total == 10
    assert report.passed == 9
    assert len(report.errors) == 1
    data = report.to_dict()
    assert TestReport.from_dict(data).failed == 1


def test_deployment_guide_serialization(deployment_guide_data: dict[str, Any]):
    guide = DeploymentGuide.from_dict(deployment_guide_data)
    assert "flask" in guide.requirements
    data = guide.to_dict()
    assert DeploymentGuide.from_dict(data).run_instructions.startswith("python")


def test_development_artifact_bundle_round_trip(
    technical_plan_data: dict[str, Any],
    feature_record_data: dict[str, Any],
    test_report_data: dict[str, Any],
    deployment_guide_data: dict[str, Any],
):
    bundle = DevelopmentArtifactBundle(
        technical_plan=TechnicalPlan.from_dict(technical_plan_data),
        feature_records=[FeatureImplementation.from_dict(feature_record_data)],
        test_report=TestReport.from_dict(test_report_data),
        deployment_guide=DeploymentGuide.from_dict(deployment_guide_data),
    )
    data = bundle.to_dict()
    restored = DevelopmentArtifactBundle.from_dict(data)
    assert restored.technical_plan.application_type == "web_app"
    assert len(restored.feature_records) == 1
    assert restored.test_report.total == 10
    assert "FLASK_ENV" in restored.deployment_guide.environment_variables


def test_development_session_state():
    session = DevelopmentSession(project_id="proj_dev")
    assert session.stage == "understanding_inputs"
    session.set_stage("technical_planning")
    assert session.stage == "technical_planning"
    assert "Stage: technical_planning" in session.logs

    plan = TechnicalPlan(application_type="website", architecture="static")
    session.update_technical_plan(plan)
    assert session.technical_plan.application_type == "website"

    record = FeatureImplementation(prd_feature="upload", status="pending")
    session.add_or_update_feature(record)
    session.add_or_update_feature(FeatureImplementation(prd_feature="Upload", status="implemented"))
    assert len(session.feature_records) == 1
    assert session.feature_records[0].status == "implemented"

    report = TestReport(total=5, passed=5)
    session.update_test_report(report)
    assert session.test_report.passed == 5

    guide = DeploymentGuide(run_instructions="run")
    session.update_deployment_guide(guide)
    assert session.deployment_guide.run_instructions == "run"


def test_development_session_invalid_stage():
    with pytest.raises(ValueError):
        DevelopmentSession(project_id="proj", stage="deployed")
    session = DevelopmentSession(project_id="proj")
    with pytest.raises(ValueError):
        session.set_stage("deployed")


def test_development_session_round_trip():
    session = DevelopmentSession(project_id="proj_x")
    session.set_stage("implementing")
    session.update_technical_plan(TechnicalPlan(application_type="ai_tool"))
    data = session.to_dict()
    restored = DevelopmentSession.from_dict(data)
    assert restored.project_id == "proj_x"
    assert restored.stage == "implementing"
    assert restored.technical_plan.application_type == "ai_tool"


def test_application_types_defined():
    assert "web_app" in VALID_APPLICATION_TYPES
    assert "ai_tool" in VALID_APPLICATION_TYPES
    assert "desktop_app" in VALID_APPLICATION_TYPES


def test_feature_statuses_defined():
    assert set(VALID_FEATURE_STATUSES) == {"pending", "implemented", "tested", "failed"}


def test_development_stages_defined():
    assert "technical_planning" in VALID_DEVELOPMENT_STAGES
    assert "completed" in VALID_DEVELOPMENT_STAGES


def test_development_decisions_set():
    assert "continue_development" in DEVELOPMENT_DECISIONS
    assert "change_stack" in DEVELOPMENT_DECISIONS
    assert "abandon" in DEVELOPMENT_DECISIONS


def test_save_technical_plan_tool(project_manager, technical_plan_data: dict[str, Any]):
    tool = SaveTechnicalPlanTool(project_manager)
    project = project_manager.create(name="Dev Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "plan": technical_plan_data})
    assert result.success, result.error
    assert "artifact_id" in result.data
    assert result.data["version"] == 1

    result2 = tool.execute("save", {"project_id": project.id, "plan": technical_plan_data})
    assert result2.success
    assert result2.data["version"] == 2


def test_save_feature_implementation_tool(project_manager, feature_record_data: dict[str, Any]):
    tool = SaveFeatureImplementationTool(project_manager)
    project = project_manager.create(name="Dev Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "record": feature_record_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_save_test_report_tool(project_manager, test_report_data: dict[str, Any]):
    tool = SaveTestReportTool(project_manager)
    project = project_manager.create(name="Dev Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "report": test_report_data})
    assert result.success, result.error
    assert result.data["version"] == 1


def test_save_deployment_guide_tool(project_manager, deployment_guide_data: dict[str, Any]):
    tool = SaveDeploymentGuideTool(project_manager)
    project = project_manager.create(name="Dev Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "guide": deployment_guide_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_record_development_decision_tool(project_manager):
    tool = RecordDevelopmentDecisionTool(project_manager)
    project = project_manager.create(name="Dev Test", goal="G")
    result = tool.execute(
        "record",
        {
            "project_id": project.id,
            "decision": "continue_development",
            "reason": "MVP stack is sufficient",
            "alternatives": ["change_stack"],
            "rejected_reasons": {"change_stack": "too complex"},
        },
    )
    assert result.success, result.error
    assert result.data["decision"] == "continue_development"

    result_invalid = tool.execute(
        "record",
        {"project_id": project.id, "decision": "invalid", "reason": "x"},
    )
    assert not result_invalid.success


def test_development_agent_prompt_forbids_scope_creep():
    from kyrozen.development.agent import SoftwareDevelopmentAgent

    config = KyrozenConfig(provider="mock", api_key="test", permission_mode="permissive")
    agent = SoftwareDevelopmentAgent(config=config, model=MockModel(), project_manager=None)
    prompt = agent._build_system_prompt()
    assert "save_technical_plan" in prompt
    assert "save_feature_implementation" in prompt
    assert "save_test_report" in prompt
    assert "save_deployment_guide" in prompt
    assert "record_development_decision" in prompt
    assert "Do NOT implement features listed in PRD.out_of_scope" in prompt
    assert "Do NOT design hardware" in prompt


def test_build_development_context_loads_prd(project_manager):
    from kyrozen.memory import InMemoryMemory
    builder = ProjectContextBuilder(project_manager, memory=InMemoryMemory())
    project = project_manager.create(name="Dev Context", goal="Build a calculator", description="simple web calc")

    brief = ProductBrief(
        product_goal=ProductGoal(product_goal="Calculator", value_proposition="fast"),
        target_user=TargetUser(primary_user="students"),
        mvp_scope=MVP(mvp_features=["add", "subtract"]),
    )
    project_manager.save_artifact(
        project.id,
        type="product_brief",
        title="Product Brief",
        content=json.dumps(brief.to_dict()),
        change_reason="Seed",
    )

    prd = PRD(
        overview="Web calculator",
        functional_requirements=["addition", "subtraction"],
        mvp_scope=MVP(mvp_features=["add", "subtract"]),
        out_of_scope=["scientific functions"],
    )
    project_manager.save_artifact(
        project.id,
        type="prd",
        title="Product Requirements Document",
        content=json.dumps(prd.to_dict()),
        change_reason="Seed",
    )

    ctx = builder.build_development_context(project)
    assert "[Software Development Context]" in ctx
    assert "Web calculator" in ctx
    assert "scientific functions" in ctx
    assert "students" in ctx


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


def _seed_product_brief_and_prd(api_client: TestClient, project_id: str) -> None:
    brief = ProductBrief(
        product_goal=ProductGoal(product_goal="Simple calculator", value_proposition="quick math"),
        target_user=TargetUser(primary_user="students"),
        mvp_scope=MVP(mvp_features=["add", "subtract"]),
    )
    api_client.post(f"/api/projects/{project_id}/artifacts", json={
        "type": "product_brief",
        "title": "Product Brief",
        "content": json.dumps(brief.to_dict()),
        "change_reason": "Seed",
    })

    prd = PRD(
        overview="A simple web calculator",
        functional_requirements=["addition", "subtraction"],
        mvp_scope=MVP(mvp_features=["add", "subtract"]),
        out_of_scope=["scientific functions"],
    )
    api_client.post(f"/api/projects/{project_id}/artifacts", json={
        "type": "prd",
        "title": "Product Requirements Document",
        "content": json.dumps(prd.to_dict()),
        "change_reason": "Seed",
    })


def test_development_chat_mode(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Dev Project", "goal": "G"})
    pid = create.json()["id"]
    _seed_product_brief_and_prd(api_client, pid)

    chat_res = api_client.post("/api/chat", json={
        "message": "开始软件开发",
        "project_id": pid,
        "mode": "development",
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["project_id"] == pid
    assert data["mode"] == "development"
    assert data["task_id"].startswith("task_")


def test_development_state_endpoint(api_client: TestClient, technical_plan_data: dict[str, Any]):
    create = api_client.post("/api/projects", json={"name": "Dev Project 2", "goal": "G"})
    pid = create.json()["id"]

    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "technical_plan",
        "title": "Technical Plan",
        "content": json.dumps(technical_plan_data),
        "change_reason": "Seed",
    })

    feature = FeatureImplementation(prd_feature="add", files=["calc.py"], tests=["test_calc.py"], status="implemented")
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "feature_implementation_record",
        "title": "Feature Implementation: add",
        "content": json.dumps(feature.to_dict()),
        "change_reason": "Seed",
    })

    report = TestReport(total=4, passed=4)
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_report",
        "title": "Test Report",
        "content": json.dumps(report.to_dict()),
        "change_reason": "Seed",
    })

    guide = DeploymentGuide(run_instructions="python calc.py", requirements=["pytest"])
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "deployment_guide",
        "title": "Deployment Guide",
        "content": json.dumps(guide.to_dict()),
        "change_reason": "Seed",
    })

    res = api_client.get(f"/api/projects/{pid}/development/state")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    assert data["technical_plan"]["application_type"] == "web_app"
    assert len(data["feature_records"]) == 1
    assert data["feature_records"][0]["prd_feature"] == "add"
    assert data["test_report"]["passed"] == 4
    assert data["deployment_guide"]["run_instructions"] == "python calc.py"


def test_development_state_requires_project(api_client: TestClient):
    res = api_client.get("/api/projects/proj_missing/development/state")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Scenario tests mapping to the three required validation cases.
# These verify that the development system can accept and persist the
# technical plan for each prototype category without inventing scope.
# ---------------------------------------------------------------------------


def test_case_simple_web_tool_technical_plan(project_manager):
    tool = SaveTechnicalPlanTool(project_manager)
    project = project_manager.create(name="Case 1: Calculator", goal="Build a calculator website")
    plan = TechnicalPlan(
        application_type="website",
        architecture="Static single-page site",
        frontend="HTML + CSS + vanilla JS",
        backend="None",
        database="None",
        deployment="Static hosting / local open",
        dependencies=[],
        rationale="A calculator needs no backend for an MVP",
    )
    result = tool.execute("save", {"project_id": project.id, "plan": plan.to_dict()})
    assert result.success, result.error
    latest = project_manager.get_latest_artifact(project.id, "technical_plan", title="Technical Plan")
    assert latest is not None
    restored = TechnicalPlan.from_dict(json.loads(latest.content))
    assert restored.application_type == "website"
    assert restored.backend == "None"


def test_case_web_app_with_database_technical_plan(project_manager):
    tool = SaveTechnicalPlanTool(project_manager)
    project = project_manager.create(name="Case 2: Todo App", goal="Build a todo web app")
    plan = TechnicalPlan(
        application_type="web_app",
        architecture="Server-rendered web app with REST API",
        frontend="HTML templates + HTMX",
        backend="Python Flask",
        database="SQLite",
        apis="REST JSON for tasks",
        deployment="Local Flask server",
        dependencies=["flask", "flask-sqlalchemy"],
        rationale="SQLite avoids external infrastructure for an MVP",
    )
    result = tool.execute("save", {"project_id": project.id, "plan": plan.to_dict()})
    assert result.success, result.error
    restored = TechnicalPlan.from_dict(
        json.loads(project_manager.get_latest_artifact(project.id, "technical_plan", title="Technical Plan").content)
    )
    assert restored.database == "SQLite"
    assert "flask" in restored.dependencies


def test_case_ai_tool_technical_plan(project_manager):
    tool = SaveTechnicalPlanTool(project_manager)
    project = project_manager.create(name="Case 3: AI Summarizer", goal="Build an AI summarizer")
    plan = TechnicalPlan(
        application_type="ai_tool",
        architecture="CLI / web wrapper around an LLM API",
        frontend="Simple web form",
        backend="Python FastAPI",
        database="None",
        apis="OpenAI-compatible chat completions API",
        deployment="Local run",
        dependencies=["fastapi", "httpx"],
        rationale="MVP only needs API key configuration and a single endpoint",
    )
    result = tool.execute("save", {"project_id": project.id, "plan": plan.to_dict()})
    assert result.success, result.error
    restored = TechnicalPlan.from_dict(
        json.loads(project_manager.get_latest_artifact(project.id, "technical_plan", title="Technical Plan").content)
    )
    assert restored.application_type == "ai_tool"
    assert "fastapi" in restored.dependencies
