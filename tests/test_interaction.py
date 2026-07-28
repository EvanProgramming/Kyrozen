"""Tests for feature 3.4: attachments, status, operation/diagnostic logs, confirmations.

Run with: ``pytest tests/test_interaction.py -q``

The image/video tests generate real media with ffmpeg (available in CI/dev) and
are skipped when ffmpeg is missing, so the deterministic, ffmpeg-free paths
(validation, status, logs, confirmations) always run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kyrozen.core import attachments as att
from kyrozen.core import confirmation as conf
from kyrozen.core import operation_log as ol
from kyrozen.core import status_state as ss
from kyrozen.tools.interaction_tools import InteractionTool


HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _make_image(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "color=c=blue:size=120x80", "-frames:v", "1", str(path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _make_video(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "testsrc=duration=2:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


# --------------------------------------------------------------------------
# Requirement #2: status bar only shows the six user-facing states
# --------------------------------------------------------------------------
def test_status_only_allows_six_states(tmp_path):
    mgr = ss.StatusManager(tmp_path)
    for state in ss.USER_FACING_STATES:
        cur = mgr.set(state, detail="x")
        assert cur["state"] == state
    with pytest.raises(ValueError):
        mgr.set("computing_model_weights")
    with pytest.raises(ValueError):
        mgr.set("")
    assert mgr.current()["state"] is None or mgr.current()["state"] in ss.USER_FACING_STATES


def test_status_clear_returns_to_idle(tmp_path):
    mgr = ss.StatusManager(tmp_path)
    mgr.set("running")
    assert mgr.current()["state"] == "running"
    mgr.clear()
    assert mgr.current()["state"] is None
    assert len(mgr.history()) >= 1


def test_status_coerce_rejects_unknown():
    assert ss.coerce_state("reading") is ss.StatusState.READING
    assert ss.coerce_state("READING") is ss.StatusState.READING
    assert ss.coerce_state("nonsense") is None


# --------------------------------------------------------------------------
# Requirement #3 + #6: operation log and diagnostic log separation
# --------------------------------------------------------------------------
def test_operation_record_duration_and_failure(tmp_path):
    log = ol.OperationLog(tmp_path)
    rid = log.start("Reading config", input_summary="read config.yaml")
    log.end(rid, output_summary="read 12 lines", status="failed", error_reason="file locked")
    records = log.list()
    assert len(records) == 1
    rec = records[0]
    assert rec["status"] == "failed"
    assert rec["error_reason"] == "file locked"
    assert rec["duration_ms"] is not None
    assert rec["duration_ms"] >= 0


def test_diagnostics_are_separated_from_operation_log(tmp_path):
    log = ol.OperationLog(tmp_path)
    dl = ol.DiagnosticsLog(tmp_path)
    rid = log.start("tool")
    log.end(rid, status="success")
    dl.append("tool_json", {"tool": "read_file", "data": {"x": 1}})
    dl.append("token_usage", {"total": 99})
    # Operation log must NOT contain diagnostic entries.
    assert all(not r.get("is_diagnostic") for r in log.list())
    kinds = {e["kind"] for e in dl.list()}
    assert kinds == {"tool_json", "token_usage"}


def test_diagnostics_reject_unknown_kind(tmp_path):
    dl = ol.DiagnosticsLog(tmp_path)
    with pytest.raises(ValueError):
        dl.append("secret_password", {"x": 1})


# --------------------------------------------------------------------------
# Requirement #1: attachments (image + video), analysis, delete
# --------------------------------------------------------------------------
def test_attachment_validation_format_and_size(tmp_path):
    mgr = att.AttachmentsManager(tmp_path, max_bytes=10)
    bad = tmp_path / "a.exe"
    bad.write_bytes(b"x")
    with pytest.raises(att.AttachmentError) as exc:
        mgr.add(bad)
    assert exc.value.reason == "format"

    big = tmp_path / "big.png"
    big.write_bytes(b"x" * 100)
    with pytest.raises(att.AttachmentError) as exc2:
        mgr.add(big)
    assert exc2.value.reason == "size"


def test_attachment_other_kind_needs_no_ffmpeg(tmp_path):
    # A non-media file is stored as 'other' without requiring ffmpeg.
    doc = tmp_path / "notes.txt"
    doc.write_text("hello")
    mgr = att.AttachmentsManager(tmp_path)
    a = mgr.add(doc)
    assert a.kind == "other"
    assert mgr.delete(a.id) is True
    assert mgr.list() == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available")
def test_image_attachment_thumbnail_and_analysis(tmp_path):
    img = tmp_path / "img.png"
    _make_image(img)
    mgr = att.AttachmentsManager(tmp_path)
    a = mgr.add(img)
    assert a.kind == "image"
    assert a.thumbnail_path and Path(a.thumbnail_path).exists()
    assert a.analysis["width"] == 120 and a.analysis["height"] == 80
    assert a.analysis["average_color"] == "#0000FD"  # blue
    # Acceptance #1: image content participates in the requirements dialogue.
    assert "img.png" in mgr.requirements_context()
    assert "120×80" in mgr.requirements_context()
    # Delete removes the file and thumbnail.
    thumb = a.thumbnail_path
    assert mgr.delete(a.id) is True
    assert not Path(thumb).exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available")
def test_video_attachment_timestamped_summary(tmp_path):
    vid = tmp_path / "vid.mp4"
    _make_video(vid)
    mgr = att.AttachmentsManager(tmp_path)
    a = mgr.add(vid)
    assert a.kind == "video"
    an = a.analysis
    assert an["duration"] == 2.0
    assert len(an["keyframes"]) == att.VIDEO_KEYFRAMES
    # Acceptance: short video produces a summary that carries timestamps.
    assert "0.4s" in an["summary"]
    assert "1.6s" in an["summary"]
    # Each keyframe has a real timestamp + extracted frame file.
    for kf in an["keyframes"]:
        assert isinstance(kf["timestamp"], (int, float))
        assert Path(kf["path"]).exists()
    # Requirements context includes the timestamped summary.
    assert "视频时长 2.0s" in mgr.requirements_context()


# --------------------------------------------------------------------------
# Requirement #4 + #5: confirmation choices, persistence, restart restore
# --------------------------------------------------------------------------
def test_confirmation_three_choices(tmp_path):
    store = conf.ConfirmationStore(tmp_path)
    c = store.create("file_write.edit_file", "编辑文件", reason="需要确认")
    assert c.status == conf.STATUS_PENDING
    assert store.resolve(c.id, "allow_once").status == conf.STATUS_ALLOWED
    assert store.resolve(store.create("git.push", "推送").id, "reject").status == conf.STATUS_REJECTED
    c3 = store.create("command.run", "运行命令")
    assert store.resolve(c3.id, "trust_project").status == conf.STATUS_TRUSTED
    assert store.is_trusted("command.run")
    with pytest.raises(ValueError):
        store.resolve(c3.id, "bogus_choice")


def test_confirm_trust_auto_allows_future(tmp_path):
    store = conf.ConfirmationStore(tmp_path)
    store.resolve(store.create("file_write.edit_file", "编辑").id, "trust_project")
    assert store.is_trusted("file_write.edit_file")
    # A later same-type op is auto-allowed and never prompts.
    c = store.create("file_write.edit_file", "再编辑")
    assert c.status == conf.STATUS_ALLOWED
    assert c.auto_allowed is True


def test_confirm_reject_blocks_execution(tmp_path):
    store = conf.ConfirmationStore(tmp_path)
    cid = store.create("git.push", "推送").id
    store.resolve(cid, "reject")
    # should_execute reflects the rejection: not allowed.
    execute, pending_id = store.should_execute("git.push")
    assert execute is False
    assert store.status_of(cid) == conf.STATUS_REJECTED


def test_confirm_restart_restores_pending_without_auto_execution(tmp_path):
    store = conf.ConfirmationStore(tmp_path)
    store.create("file_write.delete_file", "删除文件", reason="破坏性操作")
    # Simulate an app restart: a brand new store instance reads the same disk.
    restored = conf.ConfirmationStore(tmp_path).restore()
    assert len(restored) == 1
    assert restored[0].status == conf.STATUS_PENDING
    # It must NOT have been auto-executed/auto-allowed.
    assert restored[0].auto_allowed is False
    assert restored[0].status != conf.STATUS_ALLOWED


# --------------------------------------------------------------------------
# Requirement #1 (acceptance): image content participates in requirements
# --------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available")
def test_requirements_context_injects_image_and_video(tmp_path):
    img = tmp_path / "ui.png"
    _make_image(img)
    vid = tmp_path / "demo.mp4"
    _make_video(vid)
    mgr = att.AttachmentsManager(tmp_path)
    mgr.add(img)
    mgr.add(vid)
    ctx = mgr.requirements_context()
    # Both attachments contribute analyzable text, not silence.
    assert "ui.png" in ctx
    assert "demo.mp4" in ctx
    assert "视频时长" in ctx


# --------------------------------------------------------------------------
# Tool surface: every action round-trips through InteractionTool
# --------------------------------------------------------------------------
def test_interaction_tool_actions(tmp_path):
    tool = InteractionTool()
    ws = str(tmp_path)

    # status
    r = tool.execute("status_set", {"workspace_root": ws, "state": "reading"})
    assert r.success and r.data["state"] == "reading"
    assert tool.execute("status_get", {"workspace_root": ws}).data["state"] == "reading"

    # operation log
    rid = tool.execute("op_start", {"workspace_root": ws, "action": "读文件", "input_summary": "a"}).data["record_id"]
    tool.execute("op_end", {"workspace_root": ws, "record_id": rid, "status": "success"})
    assert len(tool.execute("op_list", {"workspace_root": ws}).data["records"]) == 1

    # diagnostics (must be a valid kind)
    assert tool.execute("diagnostic", {"workspace_root": ws, "kind": "token_usage", "payload": json.dumps({"n": 1})}).success
    assert not tool.execute("diagnostic", {"workspace_root": ws, "kind": "evil", "payload": "{}"}).success

    # confirmation
    c = tool.execute("confirm_create", {"workspace_root": ws, "operation_type": "git.push", "reason": "r"}).data
    assert c["status"] == "pending"
    resolved = tool.execute("confirm_resolve", {"workspace_root": ws, "confirmation_id": c["id"], "choice": "reject"}).data
    assert resolved["status"] == "rejected"
    assert tool.execute("confirm_is_trusted", {"workspace_root": ws, "operation_type": "git.push"}).data["trusted"] is False
    assert tool.execute("confirm_pending", {"workspace_root": ws}).data["pending"] == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available")
def test_interaction_tool_attach_via_jsonrpc(tmp_path):
    tool = InteractionTool()
    ws = str(tmp_path)
    img = tmp_path / "x.png"
    _make_image(img)
    r = tool.execute("attach", {"workspace_root": ws, "path": str(img)})
    assert r.success, r.error
    assert r.data["kind"] == "image"
    # Invalid format is reported (not raised) with a reason.
    bad = tmp_path / "x.zip"
    bad.write_bytes(b"x")
    r2 = tool.execute("attach", {"workspace_root": ws, "path": str(bad)})
    assert r2.success is False and r2.data["reason"] == "format"
    # Delete works through the tool.
    aid = r.data["id"]
    assert tool.execute("delete_attachment", {"workspace_root": ws, "attachment_id": aid}).data["deleted"] is True
