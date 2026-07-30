"""Software Development Agent for Kyrozen Phase 6.

The agent receives an approved PRD and Product Brief, produces a Technical Plan,
initializes a software project, writes code, runs tests, and records development
decisions.

Real-acceptance hardening (2026-07-30 round 2): the model repeatedly narrated
"Let me write the files" without executing anything, so this agent now:

1. declares ``required_actions`` -- the base loop refuses to accept a prose
   answer as completion when the user asked to build something;
2. implements ``_deterministic_fallback`` -- if the model still fails to act,
   the agent itself calls the 3.3 deterministic engine (``software_feature``
   generate + run) so a runnable project with source, README, and tests is
   guaranteed to exist on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import Task

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


#: User-input keywords that signal a real build request (vs. plain Q&A).
_BUILD_INTENT_RE = re.compile(
    r"写入|生成|创建|实现|开发|构建|搭建|做一个|做出|完成开发|写代码|编码|"
    r"index\.html|README|源码|项目文件|可运行|"
    r"\bbuild\b|\bimplement\b|\bcreate\b|\bwrite\b|\bgenerate\b|\bscaffold\b|\bcode\b",
    re.IGNORECASE,
)

_SOURCE_MARKERS = ("package.json", "pyproject.toml", "app.py", "main.py", "index.html")


class SoftwareDevelopmentAgent(BaseAgent):
    """Agent specialized in building a runnable software prototype from a PRD."""

    required_actions = ("software_feature", "file_write")

    def __init__(self, *args: Any, project_manager: "ProjectManager | None" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager

    # ------------------------------------------------------------------ hooks

    def _action_required(self, user_input: str) -> bool:
        """Only force tool execution when the user is asking to build, and the
        workspace does not already contain runnable source."""
        if not _BUILD_INTENT_RE.search(user_input or ""):
            return False
        ws = self._workspace_root()
        if ws is None:
            return True
        return not any((ws / marker).exists() for marker in _SOURCE_MARKERS)

    def _deterministic_fallback(self, task: Task, user_input: str, model_answer: str) -> str | None:
        """The model failed to write any files -- scaffold the project ourselves
        with the deterministic 3.3 engine (featuregen + BuildRunner)."""
        ws = self._workspace_root()
        if ws is None:
            return None
        try:
            gen = self.tools.execute("software_feature", "generate", {
                "workspace_root": str(ws),
                "app_type": "web_app",
                "app_name": ws.name,
                "description": user_input[:2000],
                "prd": self._load_prd_json(ws),
            })
            if not gen.success:
                self.logger.error(f"Deterministic generate failed: {gen.error}", task_id=task.id)
                return None
            run = self.tools.execute("software_feature", "run", {"workspace_root": str(ws)})
            files = (gen.data or {}).get("files", [])
            run_data = run.data or {}
            # P0-R5: the final answer shown in the main chat must describe what
            # the user got, not how the model failed. Move the "AI 未能自主写入
            # 文件" self-diagnosis out of the user-visible reply; it belongs in
            # the operations log only.
            lines = [
                f"已为你生成 {len(files)} 个项目文件（含源码、README、测试）。",
                "",
            ]
            if run.success:
                lines.append("- 构建、测试与核心流程验证：全部通过")
                if run_data.get("preview_url"):
                    lines.append(f"- 本地预览：{run_data['preview_url']}")
            else:
                lines.append(f"- 构建验证未全部通过：{run.error or '请查看操作记录'}（可让我继续修复）")
            lines += ["", "如果你想调整界面或功能，告诉我具体要改的地方即可。"]
            # P0-R5: the failed model's reasoning is not a user-facing artifact.
            # It belongs in the operations log (already attached via task.steps),
            # not the main chat reply. Drop it here.
            return "\n".join(lines)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error(f"Deterministic fallback crashed: {type(exc).__name__}: {exc}", task_id=task.id)
            return None

    # ---------------------------------------------------------------- helpers

    def _workspace_root(self) -> Path | None:
        ws = getattr(self.config, "workspace_root", None)
        if ws:
            p = Path(ws)
            if p.is_absolute() and p.exists():
                return p
        return None

    @staticmethod
    def _load_prd_json(ws: Path) -> str:
        """Best-effort: recover PRD JSON saved by the planning stage."""
        for candidate in (ws / ".kyrozen" / "prd.json", ws / "docs" / "prd.json"):
            try:
                if candidate.exists():
                    return candidate.read_text("utf-8")
            except Exception:
                pass
        return ""

    # ----------------------------------------------------------------- prompt

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Software Development Agent. Your job is to turn an approved "
            "PRD and Product Brief into a runnable software prototype with REAL files on disk.\n\n"
            "When you need to use a tool, output a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "Only reply with plain text when the user asks a question that requires no work.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "CRITICAL EXECUTION RULES:\n"
            "- When the user asks you to build, implement, or generate the product, you MUST create "
            "real files IN THE SAME TURN. NEVER end your reply with only a plan, an intention "
            "('Let me write the files', '下面开始写入'), or a promise. Announcing an action without "
            "the tool-call JSON is a failure.\n"
            "- PREFERRED PATH: call software_feature.generate (scaffolds a runnable project from the "
            "PRD: source, README, tests), then software_feature.run (install/build/test/core-flow), "
            "and software_feature.repair if the run fails. This is deterministic and reliable.\n"
            "- Use file_write to customize or extend the scaffolded files (UI text, styles, extra "
            "pages) after software_feature.generate, or for small standalone files.\n"
            "- Do NOT ask for user confirmation before writing code when the user already asked you "
            "to build -- the request IS the confirmation.\n\n"
            "Rules:\n"
            "- Always respond in the same language as the user's latest message.\n"
            "- Read the PRD and Product Brief from the context before making any plan.\n"
            "- Match the stack to the MVP. Do NOT use microservices, Kubernetes, or complex cloud "
            "architecture for simple MVPs.\n"
            "- Do NOT implement features listed in PRD.out_of_scope.\n"
            "- Do NOT add new product features that are not in the PRD. If requirements are "
            "insufficient, return to product planning instead of inventing scope.\n"
            "- Do NOT design hardware, firmware, BOM, PCB, or CAD.\n"
            "- Before implementing a feature, identify which PRD feature or functional requirement "
            "it serves and record it with save_feature_implementation.\n"
            "- Run tests with software_feature.run (preferred) or the terminal tool, and save the "
            "results with save_test_report.\n"
            "- If tests fail, use software_feature.repair or follow the debugging loop: observe, "
            "hypothesize, verify, fix, re-test.\n"
            "- Record major development decisions (stack choice, scope change) with "
            "record_development_decision.\n"
            "- Save deployment/run instructions with save_deployment_guide.\n"
            "- Commit important changes with git; include the related PRD feature in the commit message.\n"
        )
