"""Tests for the 3.3 real software generation / run / repair engine.

Covers every 3.3 requirement:
#1 spec (tech plan / dir / milestones / file tasks)
#2 real source + lockfile + keyless env + .gitignore
#3 install/build/test/core-flow execution
#4 failure -> associate task -> error summary -> modify -> rerun
#5 web preview / cli command / desktop artifact path
#6 README with goal/install/start/test/config/known-limits
#7 FeatureImplementation record
#8 non-coding deliverable templates
Plus the acceptance: a real Web product in a fresh dir starts from its README,
and a deliberately injected build failure is auto-repaired and the original test passes.
"""

from __future__ import annotations

import sys
import tempfile
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from kyrozen.core import featuregen as fg
from kyrozen.core import deliverable_templates as dt
from kyrozen.tools.software_feature_tools import SoftwareFeatureTool


# --------------------------------------------------------------------------- #
# Spec
# --------------------------------------------------------------------------- #
def test_generate_project_spec_web():
    spec = fg.generate_project_spec(
        prd={"name": "Demo", "features": ["User login", "Order query"], "description": "demo"},
        app_type="web_app",
        app_name="demo-web",
    )
    assert spec.application_type == "web_app"
    assert spec.tech_plan.application_type == "web_app"
    assert spec.prd_features == ["User login", "Order query"]
    # milestones (4) + directory structure present
    assert [m.name for m in spec.milestones][:2] == ["技术方案与目录结构", "实现核心功能"]
    assert "app.py" in spec.directory_structure
    assert "README.md" in spec.directory_structure
    # file tasks: 2 features -> 2 app tasks + 2 test tasks
    assert len(spec.file_tasks) == 4
    # unique slugs
    slugs = spec.feature_slugs()
    assert len(slugs) == 2 and len(set(slugs)) == 2
    # canonical feature values include health + each feature
    vals = spec.canonical_feature_values()
    assert vals["health"]["status"] == "ok"
    assert all(s in vals for s in slugs)


def test_generate_project_spec_cli():
    spec = fg.generate_project_spec(prd={"features": ["export csv"]}, app_type="cli_tool")
    assert spec.application_type == "cli_tool"
    assert "main.py" in spec.directory_structure
    assert "tests/test_main.py" in spec.directory_structure


def test_invalid_app_type_falls_back():
    spec = fg.generate_project_spec(app_type="not_a_type")
    assert spec.application_type == "web_app"


# --------------------------------------------------------------------------- #
# Scaffold: real files, README sections, keyless env, .gitignore
# --------------------------------------------------------------------------- #
def _scaffold_web(tmp_path: Path) -> fg.SoftwareProjectSpec:
    spec = fg.generate_project_spec(
        prd={"features": ["User login", "Order query"]}, app_type="web_app", app_name="demo"
    )
    fg.scaffold_project(spec, tmp_path)
    return spec


def test_scaffold_writes_real_files(tmp_path: Path):
    _scaffold_web(tmp_path)
    for f in ["app.py", "requirements.txt", ".env.example", ".gitignore", "README.md",
              "tests/__init__.py", "tests/test_app.py", fg.MANIFEST_FILE]:
        assert (tmp_path / f).exists(), f"missing {f}"
    # app.py is valid Python
    assert tmp_path.joinpath("app.py").read_text().count("def main()") == 1
    source = tmp_path.joinpath("app.py").read_text()
    # P0-R5: the default template is now a generic landing page, not a
    # community event registration system. Verify the new structure.
    assert "应用已就绪" in source
    assert "/api/health" in source
    assert "/api/" in source
    assert "Kyrozen 已为你生成项目骨架" in source
    assert 'id="features"' in source
    assert "暂无服务端点" in source
    assert "onclick=" not in source


def test_readme_has_required_sections(tmp_path: Path):
    _scaffold_web(tmp_path)
    readme = tmp_path.joinpath("README.md").read_text()
    for sec in ["## 目标", "## 安装", "## 启动", "## 测试", "## 配置", "## 已知限制"]:
        assert sec in readme, f"README missing {sec}"


def test_env_example_is_keyless(tmp_path: Path):
    _scaffold_web(tmp_path)
    env = tmp_path.joinpath(".env.example").read_text()
    secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    for line in env.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            key = s.split("=", 1)[0].strip().upper()
            # Non-secret config (PORT, LOG_LEVEL, URL) may carry a value;
            # secret-bearing keys must NEVER carry a value in the template.
            if any(m in key for m in secret_markers):
                value = s.split("=", 1)[1].strip()
                assert value == "", f"secret key assigned a value: {line}"


def test_gitignore_present(tmp_path: Path):
    _scaffold_web(tmp_path)
    assert ".env" in tmp_path.joinpath(".gitignore").read_text()


# --------------------------------------------------------------------------- #
# Build / run (real subprocess) — acceptance: fresh dir starts from README
# --------------------------------------------------------------------------- #
def test_build_and_test_real_subprocess(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    runner = fg.BuildRunner()
    build = runner.build(tmp_path)
    assert build.success, build.stderr
    test = runner.test(tmp_path)
    assert test.success, test.stdout + test.stderr


def test_preview_does_not_accept_an_orphan_server_health_check(tmp_path: Path):
    _scaffold_web(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        occupied_port = probe.getsockname()[1]
    env = {**os.environ, "PORT": str(occupied_port)}
    orphan = subprocess.Popen(
        [sys.executable, "app.py"], cwd=tmp_path, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{occupied_port}/health", timeout=0.2).close()
                break
            except Exception:
                time.sleep(0.05)
        run = fg.BuildRunner().start_preview(tmp_path, port=occupied_port, timeout=2)
        assert run.success, run.stderr
        # The orphan should be killed; the new preview claims the now-free port
        assert orphan.poll() is not None, "orphan preview should have been killed"
    finally:
        if orphan.poll() is None:
            orphan.terminate()
            try: orphan.wait(timeout=5)
            except Exception: orphan.kill()
        preview = fg._PREVIEW_PROCESSES.pop(str(tmp_path.resolve()), None)
        if preview and preview.poll() is None:
            fg._kill_preview_proc(preview)  # preview uses setsid, safe to killpg


def test_core_flow_runs_real_server(tmp_path: Path):
    _scaffold_web(tmp_path)
    runner = fg.BuildRunner()
    cf = runner.core_flow(tmp_path)
    assert cf.success, cf.stdout
    details = json.loads(cf.stdout)
    # health + both feature endpoints responded
    assert any(d.get("slug") == "user_login" and d.get("ok") for d in details)


def test_run_all_produces_summary_and_records(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    runner = fg.BuildRunner()
    run = runner.run_all(tmp_path, port=fg.DEFAULT_PORT)
    assert run.overall_success
    assert run.preview_url.startswith("http://localhost")
    assert run.command
    assert run.artifact_path.endswith("app.py")
    records = fg.build_feature_records(spec, run)
    assert len(records) == 2
    assert all(r.status == "tested" for r in records)
    # persistence
    saved = fg.save_software_feature(tmp_path, spec, run, feature_records=records)
    assert saved.exists()
    loaded = json.loads(saved.read_text())
    assert loaded["feature_records"]


# --------------------------------------------------------------------------- #
# Repair loop (#4) — acceptance: injected build failure auto-repaired
# --------------------------------------------------------------------------- #
def test_repair_syntax_error_restores_build(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    runner = fg.BuildRunner()
    assert runner.build(tmp_path).success
    # Inject a build (syntax) failure.
    app = tmp_path / "app.py"
    app.write_text(app.read_text().replace("def main():", "def main(  # BROKEN\n"))
    assert not runner.build(tmp_path).success
    # Repair loop on the build command.
    cmd = f"{sys.executable} -m py_compile app.py tests/*.py"
    outcome = fg.run_with_repair(runner.executor, cmd, tmp_path, file_tasks=spec.file_tasks, max_attempts=3)
    assert outcome.success, "repair should restore the build"
    assert outcome.attempts >= 1
    assert outcome.repairs[0].fix_applied
    # The matching FileTask records the repair.
    ft = next(t for t in spec.file_tasks if t.path == "app.py")
    assert ft.fix_history and ft.fix_history[0]["fix_applied"]
    # Original tests now pass.
    assert runner.test(tmp_path).success


def test_repair_assertion_restores_feature_values(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    runner = fg.BuildRunner()
    assert runner.test(tmp_path).success
    # Mutate a canonical response value so the test fails.
    app = tmp_path / "app.py"
    app.write_text(app.read_text().replace('"status": "ok"', '"status": "bad"'))
    assert not runner.test(tmp_path).success
    cmd = f"{sys.executable} -m unittest discover -s tests -p 'test_*.py'"
    outcome = fg.run_with_repair(runner.executor, cmd, tmp_path, file_tasks=spec.file_tasks, max_attempts=3)
    assert outcome.success
    restored = json.loads(
        "{" + app.read_text().split("FEATURES = {", 1)[1].split("}", 1)[0] + "}"
    ) if False else True
    assert '"status": "ok"' in app.read_text(), "FEATURES should be restored from manifest"
    assert runner.test(tmp_path).success


def test_repair_import_error_adds_requirement(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    fake = fg.CommandExecutor()
    # Monkeypatch a fake executor whose first run fails with ImportError.
    class FakeExec(fg.CommandExecutor):
        def __init__(self):
            self.calls = 0
        def run(self, cwd, command, timeout=180.0):
            self.calls += 1
            if self.calls == 1:
                return fg.RunResult(command=command, exit_code=1,
                                    stderr="ImportError: No module named 'requests'")
            return fg.RunResult(command=command, exit_code=0, stdout="ok")
    outcome = fg.run_with_repair(FakeExec(), "pip install -r requirements.txt", tmp_path,
                                 file_tasks=spec.file_tasks, max_attempts=3)
    assert outcome.success
    assert "requests" in (tmp_path / "requirements.txt").read_text()
    assert outcome.repairs[-1].fix_applied


def test_repair_gives_up_when_no_strategy(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    class FakeExec(fg.CommandExecutor):
        def run(self, cwd, command, timeout=180.0):
            return fg.RunResult(command=command, exit_code=2, stderr="RuntimeError: boom")
    outcome = fg.run_with_repair(FakeExec(), "whatever", tmp_path, max_attempts=3)
    assert not outcome.success
    assert outcome.attempts == 0  # no strategy -> stop immediately


# --------------------------------------------------------------------------- #
# FeatureImplementation status reflects run outcome
# --------------------------------------------------------------------------- #
def test_feature_records_failed_when_unrepairable(tmp_path: Path):
    spec = _scaffold_web(tmp_path)
    runner = fg.BuildRunner()
    # Delete the tests dir so the test step fails and cannot be repaired.
    import shutil
    shutil.rmtree(tmp_path / "tests")
    run = runner.run_all(tmp_path)
    assert not run.overall_success
    records = fg.build_feature_records(spec, run)
    assert all(r.status == "failed" for r in records)


# --------------------------------------------------------------------------- #
# Non-coding deliverables (#8)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("dtype", ["research_report", "content_plan", "ops_plan", "business_process"])
def test_noncoding_templates_render(dtype, tmp_path: Path):
    fields = {s["name"]: (f"值-{s['name']}" if s["kind"] == "text" else [f"项1", f"项2"])
              for s in dt.NONCODING_SCHEMAS[dtype]}
    # add the required list fields properly
    res = dt.build_deliverable(dtype, "示例交付物", fields, tmp_path)
    md = res.markdown
    assert res.deliverable_type == dtype
    assert (tmp_path / res.file).exists()
    # deliverables.json persisted
    log = json.loads((tmp_path / ".kyrozen" / "deliverables.json").read_text())
    assert any(d["deliverable_type"] == dtype for d in log)
    # markdown contains the field values
    assert "值-background" in md or "项1" in md


def test_noncoding_unknown_type_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        dt.build_deliverable("nope", "x", {}, tmp_path)


def test_noncoding_accepts_plain_chinese_field_labels(tmp_path: Path):
    res = dt.build_deliverable(
        "research_report",
        "社区活动报名竞品调研报告",
        {"背景": "微信群接龙容易漏人", "对比对象": "微信接龙、问卷星", "重点": "无需注册和名额控制", "结论": "先做轻量报名工具"},
        tmp_path,
    )
    assert "微信群接龙容易漏人" in res.markdown
    assert "微信接龙、问卷星" in res.markdown
    assert "先做轻量报名工具" in res.markdown


# --------------------------------------------------------------------------- #
# Tool integration
# --------------------------------------------------------------------------- #
def test_tool_generate_and_run_real(tmp_path: Path):
    tool = SoftwareFeatureTool(executor=fg.CommandExecutor())
    gen = tool.execute("generate", {
        "workspace_root": str(tmp_path),
        "app_type": "web_app",
        "prd": json.dumps({"features": ["User login", "Order query"]}),
    })
    assert gen.success
    run = tool.execute("run", {"workspace_root": str(tmp_path)})
    assert run.success, run.error
    data = run.data
    assert data["run"]["overall_success"]
    assert data["preview_url"]
    assert len(data["feature_records"]) == 2
    # persisted locally
    assert (tmp_path / ".kyrozen" / "software_feature.json").exists()


def test_tool_uses_bound_desktop_workspace_over_stale_model_path(tmp_path: Path):
    from kyrozen.config import KyrozenConfig

    tool = SoftwareFeatureTool(config=KyrozenConfig(workspace_root=str(tmp_path)))
    assert tool._resolve_workspace({"workspace_root": "/projects/proj-stale"}) == str(tmp_path)


def test_tool_repair_real(tmp_path: Path):
    tool = SoftwareFeatureTool(executor=fg.CommandExecutor())
    tool.execute("generate", {"workspace_root": str(tmp_path), "app_type": "web_app",
                              "prd": json.dumps({"features": ["User login"]})})
    # inject syntax error
    app = tmp_path / "app.py"
    app.write_text(app.read_text().replace("def main():", "def main(  # BROKEN\n"))
    rep = tool.execute("repair", {"workspace_root": str(tmp_path)})
    assert rep.success, rep.data.get("repair")
    assert rep.data["repair"]["success"]


def test_tool_noncoding(tmp_path: Path):
    tool = SoftwareFeatureTool()
    res = tool.execute("noncoding", {
        "workspace_root": str(tmp_path),
        "deliverable_type": "research_report",
        "title": "竞品研究",
        "fields": json.dumps({"background": "背景", "question": "问题",
                              "findings": ["发现1", "发现2"], "conclusion": "结论"}),
    })
    assert res.success
    assert (tmp_path / res.data["file"]).exists()
    assert "背景" in res.data["markdown"]
