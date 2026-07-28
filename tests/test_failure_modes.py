"""3.6 #3 — 故障场景集成测试。

直接针对真实代码路径验证文档要求的六种故障模式都能被优雅处理，而不是崩溃：

1. 模型超时   -> kyrozen.desktop.cloud_proxy.CloudProxyModelProvider（120s 超时）
2. 网络中断   -> kyrozen.models.providers.OpenAICompatProvider（不可达 base_url）
3. API 限流   -> OpenAICompatProvider（mock 429 + _retry_with_backoff）
4. 工具失败   -> kyrozen.tools.base.Tool.execute 的 try/except 包裹
5. 拒绝确认   -> kyrozen.core.confirmation.ConfirmationStore（reject + restore）
6. 磁盘写入失败 -> Tool 在只读目录写入被捕获为 success=False

这些测试不依赖真实模型或后端，可在任意环境运行，作为 3.6 发布门槛中
“覆盖模型超时 / 网络中断 / API 限流 / 工具失败 / 拒绝确认 / 磁盘写入失败”
的可执行证据。
"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from kyrozen.config import KyrozenConfig
from kyrozen.core.confirmation import ConfirmationStore
from kyrozen.desktop.cloud_proxy import CloudProxyModelProvider
from kyrozen.models.providers import OpenAICompatProvider
from kyrozen.tools.base import Tool, ToolParameter, ToolResult, ToolSchema


# --------------------------------------------------------------------------- #
# 4. 工具失败                                                                  #
# --------------------------------------------------------------------------- #
class _BoomTool(Tool):
    name = "boom"
    description = "always raises"
    schema = ToolSchema(name="boom", description="", actions={"run": []})

    def _execute(self, action: str, parameters: dict) -> ToolResult:
        raise RuntimeError("kaboom simulated failure")


def test_tool_failure_is_caught_and_reported():
    result = _BoomTool().execute("run", {})
    assert result.success is False
    assert "RuntimeError" in result.error
    assert "kaboom simulated failure" in result.error


# --------------------------------------------------------------------------- #
# 6. 磁盘写入失败                                                              #
# --------------------------------------------------------------------------- #
class _WriteTool(Tool):
    name = "writer"
    description = "writes a file"
    schema = ToolSchema(
        name="writer",
        description="",
        actions={"write": [ToolParameter("path", "string", "target path")]},
    )

    def _execute(self, action: str, parameters: dict) -> ToolResult:
        Path(parameters["path"]).write_text("should not succeed")
        return ToolResult(success=True, data=None)


def test_disk_write_failure_is_caught(tmp_path: Path):
    readonly = tmp_path / "ro"
    readonly.mkdir()
    # 移除写权限，使非 root 进程无法在其中创建文件（macOS/Linux）。
    os.chmod(readonly, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    try:
        target = readonly / "out.txt"
        result = _WriteTool().execute("write", {"path": str(target)})
        assert result.success is False
        assert "PermissionError" in result.error
        assert not target.exists()
    finally:
        os.chmod(readonly, stat.S_IRWXU)


# --------------------------------------------------------------------------- #
# 1. 模型超时                                                                  #
# --------------------------------------------------------------------------- #
def test_model_timeout_raises_instead_of_hanging():
    provider = CloudProxyModelProvider(send_message=lambda m: None)  # never responds

    original = asyncio.wait_for

    async def fast_wait_for(fut, timeout=120):
        return await original(fut, timeout=0.1)

    with mock.patch.object(asyncio, "wait_for", fast_wait_for):
        with pytest.raises(asyncio.TimeoutError):
            provider.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# 2. 网络中断                                                                  #
# --------------------------------------------------------------------------- #
def test_network_interruption_is_reported():
    config = KyrozenConfig(
        provider="deepseek",
        api_key="sk-test",
        base_url="http://127.0.0.1:9",  # nothing listening -> connection refused
        model_simple="deepseek-chat",
    )
    provider = OpenAICompatProvider(config)
    with pytest.raises(Exception):
        provider.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# 3. API 限流                                                                  #
# --------------------------------------------------------------------------- #
def test_api_rate_limit_retries_then_fails():
    """模拟模型 API 返回 429（限流），验证提供商的退避重试后优雅失败。

    直接驱动真实的 OpenAICompatProvider._retry_with_backoff 路径：
    - 检测到 429/rate limit 关键字后重试（最多 3 次）；
    - 最终抛出包含限流信息的异常，而不是无限挂起或崩溃。
    """
    config = KyrozenConfig(
        provider="deepseek",
        api_key="sk-test",
        base_url="http://unused.example/v1",
        model_simple="deepseek-chat",
    )
    provider = OpenAICompatProvider(config)

    calls = {"n": 0}

    def _fake_create(**_kwargs):
        calls["n"] += 1
        # 模拟上游限流响应
        raise RuntimeError("429 Too Many Requests: rate limit exceeded")

    provider._client = mock.MagicMock()
    provider._client.chat.completions.create.side_effect = _fake_create

    # 加速退避，避免测试过慢。
    with mock.patch("kyrozen.models.providers.time.sleep", lambda *a, **k: None), mock.patch(
        "kyrozen.models.providers.random.uniform", lambda *a, **k: 0.0
    ):
        with pytest.raises(Exception) as exc:
            provider.chat([{"role": "user", "content": "hi"}])

    assert "429" in str(exc.value).lower() or "rate limit" in str(exc.value).lower()
    # 初始调用 + 3 次退避重试 = 4 次
    assert calls["n"] >= 4


# --------------------------------------------------------------------------- #
# 5. 拒绝确认 + 重启恢复                                                       #
# --------------------------------------------------------------------------- #
def test_confirmation_reject_and_restore(tmp_path: Path):
    store = ConfirmationStore(tmp_path)

    # should_execute 对未信任操作创建待确认项并返回 (False, pending_id)
    ok, pid = store.should_execute("file_write")
    assert ok is False
    assert store.status_of(pid) == "pending"

    # 用户拒绝 -> 操作绝不执行
    resolved = store.resolve(pid, "reject")
    assert resolved is not None
    assert resolved.status == "rejected"

    # 拒绝不是“信任”：下一次相同操作仍需重新确认（绝不一键自动执行）
    ok2, pid2 = store.should_execute("file_write")
    assert ok2 is False
    assert store.status_of(pid2) == "pending"

    # 模拟“重启”：新实例从磁盘恢复待确认项（拒绝项不会被自动执行）
    store2 = ConfirmationStore(tmp_path)
    restored = store2.restore()
    assert any(c.id == pid2 for c in restored)

    # trust_project 路径：信任后 should_execute 直接放行
    push_ok, push_pid = store2.should_execute("git_push")
    assert push_ok is False
    store2.resolve(push_pid, "trust_project")
    assert store2.is_trusted("git_push") is True
    ok3, pid3 = store2.should_execute("git_push")
    assert ok3 is True
    assert pid3 is None

    # allow_once 是单次授权：下一次相同操作仍需确认
    term_ok, term_pid = store2.should_execute("run_terminal")
    store2.resolve(term_pid, "allow_once")
    assert store2.status_of(term_pid) == "allowed"
    ok4, _ = store2.should_execute("run_terminal")
    assert ok4 is False

    # 非法选择必须被拒绝
    with pytest.raises(ValueError):
        store2.resolve(term_pid, "not_a_choice")
