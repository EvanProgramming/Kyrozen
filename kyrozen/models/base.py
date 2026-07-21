"""Unified model interface for Kyrozen Core.

Business logic must use ModelInterface, not concrete providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Usage:
    """Token usage for a model call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ModelResponse:
    """Standard model response."""

    content: str
    usage: Usage | None = None
    model: str = ""
    provider: str = ""


class ModelInterface(ABC):
    """Abstract model interface."""

    def __init__(self, model: str = "") -> None:
        self.model = model

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        """Non-streaming chat completion."""
        ...

    def chat_stream(self, messages: list[dict[str, str]], model: str | None = None) -> Iterator[str]:
        """Streaming chat completion. Default falls back to chat()."""
        response = self.chat(messages, model)
        yield response.content

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
