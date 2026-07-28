"""Membership rules for complete-project access in the desktop client."""

from fastapi.testclient import TestClient

from kyrozen.config import KyrozenConfig
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
