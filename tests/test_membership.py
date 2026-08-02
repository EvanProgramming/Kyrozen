"""Membership rules for complete-project access in the desktop client."""

from fastapi.testclient import TestClient

from kyrozen.config import KyrozenConfig
from kyrozen.membership import MembershipService, UsageEstimate
from kyrozen.project import KyrozenDatabase
from tests.conftest import MockModel, TEST_USER, make_authenticated_app


def _client(temp_dir: str, *, developer: bool = False) -> TestClient:
    config = KyrozenConfig(
        provider="ollama",
        workspace_root=temp_dir,
        task_store_path=f"{temp_dir}/tasks.json",
        free_project_limit=1,
        developer_user_ids=[TEST_USER.user_id] if developer else [],
        developer_github_users=[],
    )
    return TestClient(make_authenticated_app(config, MockModel(["OK"])))


def test_free_account_can_create_one_complete_project(temp_dir: str):
    with _client(temp_dir) as client:
        assert client.post("/api/projects", json={"name": "First"}).status_code == 200
        blocked = client.post("/api/projects", json={"name": "Second"})
        assert blocked.status_code == 403
        assert "完整使用全部阶段" in blocked.json()["detail"]
        assert client.get("/api/desktop/quota").json()["allowed"] is True


def test_developer_account_is_unlimited(temp_dir: str):
    with _client(temp_dir, developer=True) as client:
        assert client.post("/api/projects", json={"name": "First"}).status_code == 200
        assert client.post("/api/projects", json={"name": "Second"}).status_code == 200
        membership = client.get("/api/desktop/quota").json()
        assert membership["plan"] == "developer"
        assert membership["project_limit"] == 0


def test_free_delete_does_not_restore_monthly_creation(temp_dir: str):
    with _client(temp_dir) as client:
        first = client.post("/api/projects", json={"name": "First"})
        assert first.status_code == 200
        project_id = first.json()["id"]
        assert client.delete(f"/api/projects/{project_id}").status_code == 200
        blocked = client.post("/api/projects", json={"name": "Replacement"})
        assert blocked.status_code == 403
        assert "订阅月最多创建" in blocked.json()["detail"]


def test_lite_tracks_active_and_monthly_creation_separately(temp_dir: str):
    db = KyrozenDatabase(f"{temp_dir}/kyrozen.db")
    service = MembershipService(db)
    service.set_plan("owner", "lite")
    for index in range(5):
        allowed, reason = service.project_decision("owner", index)
        assert allowed, reason
        service.record_project_creation("owner", f"project-{index}")
    assert service.project_decision("owner", 4)[0] is False
    assert "创建" in service.project_decision("owner", 0)[1]


def test_usage_formula_and_rolling_window_limits(temp_dir: str):
    service = MembershipService(KyrozenDatabase(f"{temp_dir}/kyrozen.db"))
    service.set_plan("owner", "lite")
    estimate = service.estimate(prompt_tokens=1000, completion_tokens=1000, cache_hit_tokens=100, tool_calls=2)
    assert estimate.credits > 2
    assert estimate.cost_rmb > 0
    service.record_usage("owner", UsageEstimate(credits=750, cost_rmb=0, prompt_tokens=1), kind="model")
    decision = service.check("owner", UsageEstimate(credits=1, cost_rmb=0))
    assert decision["allowed"] is False
    assert "5小时" in decision["reason"]


def test_ultimate_family_members_share_usage(temp_dir: str):
    service = MembershipService(KyrozenDatabase(f"{temp_dir}/kyrozen.db"))
    service.set_plan("owner", "ultimate")
    service.add_seat("owner", "child")
    service.record_usage("child", UsageEstimate(credits=100, cost_rmb=10, prompt_tokens=1))
    status = service.status("owner")
    assert status["monthly_cost_rmb"] == 10
    assert service.status("child")["monthly_cost_rmb"] == 10
