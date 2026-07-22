"""Shared fixtures for Kyrozen tests."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.auth.context import current_user_ctx
from kyrozen.auth.dependencies import CurrentUser, get_current_user
from kyrozen.config import KyrozenConfig
from kyrozen.learning.repository import LearningRepository
from kyrozen.models.base import ModelInterface, ModelResponse
from kyrozen.project import KyrozenDatabase, ProjectManager


TEST_USER = CurrentUser(
    user_id="test_user",
    email="test@example.com",
    name="Test User",
    role="user",
)


class MockModel(ModelInterface):
    """A deterministic model for testing agent loops."""

    def __init__(self, responses: list[str] | None = None) -> None:
        super().__init__(model="mock")
        self.responses = responses or []
        self.calls: list[list[dict[str, str]]] = []
        self.index = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        self.calls.append(messages)
        text = ""
        if self.responses:
            text = self.responses[self.index % len(self.responses)]
        self.index += 1
        return ModelResponse(content=text, model="mock", provider="mock")


@pytest.fixture
def temp_dir() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def test_config(temp_dir: str) -> KyrozenConfig:
    return KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="permissive",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
        memory_backend="memory",
        chroma_path=os.path.join(temp_dir, "chroma"),
    )


@pytest.fixture
def project_manager(test_config: KyrozenConfig) -> Iterator[ProjectManager]:
    db = KyrozenDatabase(test_config.db_path)
    pm = ProjectManager(db)
    yield pm


@pytest.fixture
def learning_repository(project_manager: ProjectManager) -> Iterator[LearningRepository]:
    repo = LearningRepository(project_manager.db)
    token = current_user_ctx.set(TEST_USER)
    try:
        yield repo
    finally:
        current_user_ctx.reset(token)


def make_authenticated_app(config: KyrozenConfig, model: ModelInterface | None = None) -> Any:
    """Create a FastAPI app with authentication overridden for tests."""
    app = create_app(config=config, model=model)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    return app


@pytest.fixture
def auth_client(test_config: KyrozenConfig) -> Iterator[TestClient]:
    """Authenticated TestClient using the shared test user."""
    app = make_authenticated_app(test_config, MockModel())
    with TestClient(app) as client:
        yield client
