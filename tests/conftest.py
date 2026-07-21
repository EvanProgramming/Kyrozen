"""Shared fixtures for Kyrozen tests."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Iterator

import pytest

from kyrozen.config import KyrozenConfig
from kyrozen.models.base import ModelInterface, ModelResponse


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
