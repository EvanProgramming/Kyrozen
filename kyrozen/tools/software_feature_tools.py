"""Tool exposing the 3.3 real software generation / run / repair engine.

The ``SoftwareDevelopmentAgent`` (and the desktop ``development`` mode) can now
call *deterministic* capabilities instead of relying purely on the LLM to write
correct code:

- ``generate``  -- scaffold a runnable project from a confirmed PRD
- ``run``       -- install / build / test / core-flow and record FeatureImplementation
- ``repair``    -- run a command through the error->locate->fix->rerun loop
- ``noncoding`` -- produce a typed non-software deliverable

Results are persisted to ``<workspace>/.kyrozen/`` so they survive reopening.
"""

from __future__ import annotations

import json
from typing import Any

from kyrozen.core import deliverable_templates as dt
from kyrozen.core import featuregen as fg
from kyrozen.tools.base import Tool, ToolResult, ToolSchema, ToolParameter


def _parse_prd(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _parse_fields(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


class SoftwareFeatureTool(Tool):
    name = "software_feature"
    description = "真实软件生成、运行与修复：从 PRD 搭建可运行项目、执行构建/测试、失败自动修复、生成非编码交付物。"
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "generate": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("app_type", "string", "web_app | cli_tool | ...（默认 web_app）", required=False),
                ToolParameter("app_name", "string", "应用名称", required=False),
                ToolParameter("description", "string", "应用描述", required=False),
                ToolParameter("prd", "string", "确认后的 PRD JSON（含 features 列表）", required=False),
            ],
            "run": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("port", "integer", "Web 预览端口（默认 8000）", required=False),
            ],
            "repair": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("command", "string", "需要带修复重跑的命令（默认构建命令）", required=False),
                ToolParameter("max_attempts", "integer", "最大修复次数（默认 3）", required=False),
            ],
            "noncoding": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("deliverable_type", "string", "research_report|content_plan|ops_plan|business_process", required=True),
                ToolParameter("title", "string", "交付物标题", required=True),
                ToolParameter("fields", "string", "字段 JSON 对象", required=False),
            ],
        },
    )

    def __init__(self, project_manager: Any = None, executor: fg.CommandExecutor | None = None) -> None:
        super().__init__()
        self.project_manager = project_manager
        self.executor = executor or fg.CommandExecutor()

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if action == "generate":
            return self._generate(parameters)
        if action == "run":
            return self._run(parameters)
        if action == "repair":
            return self._repair(parameters)
        if action == "noncoding":
            return self._noncoding(parameters)
        return ToolResult(success=False, data=None, error=f"Unsupported action '{action}'")

    def _generate(self, params: dict[str, Any]) -> ToolResult:
        ws = str(params.get("workspace_root"))
        if not ws:
            return ToolResult(success=False, data=None, error="workspace_root is required")
        prd = _parse_prd(params.get("prd"))
        spec = fg.generate_project_spec(
            prd,
            app_type=str(params.get("app_type") or "web_app"),
            app_name=params.get("app_name"),
            description=str(params.get("description") or ""),
        )
        result = fg.scaffold_project(spec, ws)
        return ToolResult(
            success=True,
            data={
                "spec": spec.to_dict(),
                "files": result.files,
                "manifest_path": result.manifest_path,
                "message": f"已在 {ws} 生成可运行项目（{spec.application_type}），按 README 即可启动。",
            },
        )

    def _run(self, params: dict[str, Any]) -> ToolResult:
        ws = str(params.get("workspace_root"))
        if not ws:
            return ToolResult(success=False, data=None, error="workspace_root is required")
        port = int(params.get("port") or fg.DEFAULT_PORT)
        manifest = fg.load_manifest(ws)
        spec = fg.SoftwareProjectSpec.from_dict(manifest.get("spec", {})) if manifest else fg.generate_project_spec(app_type="web_app")
        runner = fg.BuildRunner(self.executor)
        run = runner.run_all(ws, port=port)
        records = fg.build_feature_records(spec, run)
        run.feature_records = records
        saved = fg.save_software_feature(ws, spec, run, feature_records=records)
        return ToolResult(
            success=run.overall_success,
            data={
                "run": run.to_dict(),
                "feature_records": [r.to_dict() for r in records],
                "preview_url": run.preview_url,
                "command": run.command,
                "artifact_path": run.artifact_path,
                "saved_path": str(saved),
            },
            error="" if run.overall_success else "部分阶段失败，请查看 run 详情或使用 repair。",
        )

    def _repair(self, params: dict[str, Any]) -> ToolResult:
        ws = str(params.get("workspace_root"))
        if not ws:
            return ToolResult(success=False, data=None, error="workspace_root is required")
        manifest = fg.load_manifest(ws)
        spec = fg.SoftwareProjectSpec.from_dict(manifest.get("spec", {})) if manifest else fg.generate_project_spec(app_type="web_app")
        command = str(params.get("command") or f"{__import__('sys').executable} -m py_compile app.py tests/*.py")
        max_attempts = int(params.get("max_attempts") or 3)
        outcome = fg.run_with_repair(self.executor, command, ws, file_tasks=spec.file_tasks, max_attempts=max_attempts)
        # Persist the repair trail + re-evaluate feature records.
        run = fg.BuildRunner(self.executor).run_all(ws, port=fg.DEFAULT_PORT)
        records = fg.build_feature_records(spec, run)
        run.feature_records = records
        saved = fg.save_software_feature(ws, spec, run, feature_records=records)
        return ToolResult(
            success=outcome.success,
            data={
                "repair": outcome.to_dict(),
                "feature_records": [r.to_dict() for r in records],
                "saved_path": str(saved),
            },
            error="" if outcome.success else "修复未成功，请查看 repair 详情。",
        )

    def _noncoding(self, params: dict[str, Any]) -> ToolResult:
        ws = str(params.get("workspace_root"))
        dtype = str(params.get("deliverable_type") or "")
        title = str(params.get("title") or "未命名交付物")
        fields = _parse_fields(params.get("fields"))
        if dtype not in dt.NONCODING_TYPES:
            return ToolResult(success=False, data=None, error=f"未知交付类型 '{dtype}'")
        try:
            result = dt.build_deliverable(dtype, title, fields, ws)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(success=False, data=None, error=f"{type(exc).__name__}: {exc}")
        return ToolResult(
            success=True,
            data={
                "deliverable_type": result.deliverable_type,
                "title": result.title,
                "file": result.file,
                "markdown": result.markdown,
            },
        )
