"""Tests for Kyrozen configuration."""

from __future__ import annotations

import os

import pytest

from kyrozen.config import KyrozenConfig, get_config
from kyrozen.config.settings import PROVIDER_DEFAULT_MODELS


def test_default_config():
    cfg = KyrozenConfig(provider="deepseek", api_key="test-key")
    assert cfg.provider == "deepseek"
    assert cfg.model_simple == PROVIDER_DEFAULT_MODELS["deepseek"][0]
    assert cfg.permission_mode == "strict"
    assert cfg.workspace_root == os.path.abspath(".")


def test_validate_missing_key():
    cfg = KyrozenConfig(provider="openai", api_key="")
    issues = cfg.validate()
    assert any("OPENAI_API_KEY" in issue for issue in issues)


def test_validate_ok():
    cfg = KyrozenConfig(provider="deepseek", api_key="test-key")
    assert cfg.validate() == []


def test_get_config_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("KYROZEN_PERMISSION_MODE", "permissive")
    cfg = get_config()
    assert cfg.provider == "deepseek"
    assert cfg.api_key == "env-key"
    assert cfg.permission_mode == "permissive"
