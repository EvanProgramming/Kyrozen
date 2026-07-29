"""Python Agent Runtime entry point for Kyrozen Desktop Client.

Reads JSON-RPC requests from stdin and writes responses to stdout.
Communicates with the Electron main process via stdio.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path

# Make the repository root importable so we can reuse kyrozen core modules.
REPO_ROOT = Path(os.environ.get("KYROZEN_RESOURCE_ROOT", Path(__file__).resolve().parents[2])).resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kyrozen.config import get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.handoff import HandoffStore, HandoffTool
from kyrozen.core.router import AgentRouter, LocalCapabilities
from kyrozen.core.stagegate import (
    STAGES,
    StageGateStore,
    compute_gate,
    compute_progress,
    get_status,
    refresh_gate,
    advance,
)
from kyrozen.core.task import Task
from kyrozen.core import featuregen as featuregen_mod
from kyrozen.core import deliverable_templates as deliverable_mod
from kyrozen.core import attachments as attachments_mod
from kyrozen.core import status_state as status_mod
from kyrozen.core import operation_log as operation_mod
from kyrozen.core import confirmation as confirmation_mod
from kyrozen.desktop import CloudProxyModelProvider
from kyrozen.logs import get_logger
from kyrozen.memory import InMemoryMemory
from kyrozen.tools import get_default_registry


class PendingConfirmation:
    """Thread-safe container for an outstanding user confirmation."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: bool = False
        self.trust_for_session: bool = False
        self.store_id: str | None = None


def _make_ai_image_analyzer() -> "attachments_mod.AIImageAnalyzer | None":
    """Build an image analyzer using OmniRoute vision (fallback: Gemini direct)."""
    import urllib.request, urllib.error

    def chat_fn(messages: list, *, model_name: str = "auto/vision") -> dict:
        providers = [
            ("https://kyrozen.chat/ai/v1/chat/completions", {"Authorization": "Bearer auto"}),
            (f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={os.environ.get('GEMINI_API_KEY', '')}", {}),
        ]
        last_error = None
        for url, headers in providers:
            try:
                if "generativelanguage" in url:
                    import base64 as b64mod
                    text_parts = []
                    for m in messages:
                        content = m.get("content", "")
                        if isinstance(content, list):
                            for part in content:
                                if part.get("type") == "text":
                                    text_parts.append(part["text"])
                                elif part.get("type") == "image_url":
                                    data_url = part["image_url"]["url"]
                                    if data_url.startswith("data:"):
                                        b64_data = data_url.split(",", 1)[1]
                                        text_parts.append({"inline_data": {"mime_type": "image/png", "data": b64_data}})
                        else:
                            text_parts.append(str(content))
                    body = json.dumps({"contents": [{"parts": text_parts}]}).encode()
                    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read())
                        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        return {"content": text}
                else:
                    body = json.dumps({
                        "model": "auto/vision",
                        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                        "max_tokens": 100,
                    }).encode()
                    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read())
                        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        return {"content": text}
            except Exception as e:
                last_error = e
                continue
        raise last_error or RuntimeError("No vision provider available")

    return attachments_mod.AIImageAnalyzer(chat_fn=chat_fn)


def _make_asr_fn():
    """Build a Gemini-based speech-to-text function for video transcription."""
    import urllib.request, subprocess, tempfile

    def asr_fn(video_path):
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return None, []
        # Extract audio as MP3 via ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
                 "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", tmp_path],
                check=True, timeout=60,
            )
            audio_bytes = Path(tmp_path).read_bytes()
            import base64 as b64mod
            b64 = b64mod.b64encode(audio_bytes).decode("ascii")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            body = json.dumps({
                "contents": [{"parts": [
                    {"text": "请将这段音频转录为中文文本，按时间点分段输出。格式：每行 'MM:SS 文本内容'"},
                    {"inline_data": {"mime_type": "audio/mp3", "data": b64}},
                ]}],
            }).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            # Parse timestamped lines into segments
            from kyrozen.core.attachments import TranscriptSegment
            import re
            segments = []
            for line in (text or "").splitlines():
                m = re.match(r"(\d+):(\d+)\s+(.+)", line.strip())
                if m:
                    mins, secs, content = int(m.group(1)), int(m.group(2)), m.group(3)
                    t = mins * 60 + secs
                    segments.append(TranscriptSegment(start=t, end=t + 5, text=content))
                elif line.strip():
                    segments.append(TranscriptSegment(start=len(segments) * 5, end=len(segments) * 5 + 5, text=line.strip()))
            return text, segments
        except Exception:
            return None, []
        finally:
            try: Path(tmp_path).unlink(missing_ok=True)
            except Exception: pass

    return asr_fn


class PlanDetectingModelProvider:
    """Wraps a model provider and emits the first execution plan it detects."""

    def __init__(self, inner: CloudProxyModelProvider, on_plan: callable) -> None:
        self._inner = inner
        self._on_plan = on_plan
        self._emitted_for_task = False

    def reset_plan(self) -> None:
        self._emitted_for_task = False

    def chat(self, messages, model=None):
        response = self._inner.chat(messages, model=model)
        self._maybe_emit_plan(response.content)
        return response

    def chat_stream(self, messages, model=None):
        chunks = list(self._inner.chat_stream(messages, model=model))
        self._maybe_emit_plan("".join(chunks))
        return iter(chunks)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def _maybe_emit_plan(self, text: str) -> None:
        if self._emitted_for_task:
            return
        plan = self._extract_plan_steps(text)
        if plan:
            self._emitted_for_task = True
            self._on_plan(plan)

    def _extract_plan_steps(self, text: str) -> list[str] | None:
        lines = text.splitlines()
        marker_re = re.compile(r"^\s*(?:[-*]|\d+[.\)])\s+(.+)$")
        plan_heading = False
        steps: list[str] = []
        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()
            if any(keyword in lower for keyword in ("执行计划", "计划", "plan", "steps", "步骤")):
                plan_heading = True
            match = marker_re.match(line)
            if match:
                steps.append(match.group(1).strip())
        # Emit if we see a plan heading with at least one step, or two+ steps without heading.
        if steps and (plan_heading or len(steps) >= 2):
            return steps[:10]
        return None


class DesktopAgentRuntime:
    """Minimal local agent runtime that talks to Electron over stdio JSON-RPC."""

    # Default timeout for a local task (seconds). Can be overridden per task.
    DEFAULT_TASK_TIMEOUT_SECONDS = 600

    def __init__(self) -> None:
        self.config = get_config()
        self.logger = get_logger(self.config.log_level)
        self.send_message: callable | None = None
        self.model: CloudProxyModelProvider | None = None
        self.agent: BaseAgent | None = None
        self.router = AgentRouter()
        self.current_task_id: str | None = None
        self.current_task: Task | None = None
        self._pending_confirmations: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()
        self._task_thread: threading.Thread | None = None
        self._task_timeout_timer: threading.Timer | None = None
        self._task_timed_out = threading.Event()

    def set_send_message(self, send_message: callable) -> None:
        """Bind the function used to send JSON-RPC messages to Electron."""
        self.send_message = send_message
        inner_model = CloudProxyModelProvider(send_message=send_message)
        self.model = PlanDetectingModelProvider(inner_model, self._emit_execution_plan)
        tools = get_default_registry()
        self.agent = BaseAgent(
            config=self.config,
            model=self.model,
            tools=tools,
            memory=InMemoryMemory(),
            logger=self.logger,
            confirmation_callback=self._request_confirmation,
        )
        self._wrap_tool_execution(tools)
        # Signal readiness so the desktop UI stops showing an undefined/loading
        # state and can detect an Agent that fails later (P0-03/P0-04/P0-06).
        from kyrozen import __version__ as kyrozen_version

        self._notify("ready", {
            "status": "ready",
            "version": getattr(self.config, "version", "") or kyrozen_version,
            "mode": getattr(self.config, "permission_mode", "strict"),
        })

    def handle_request(self, request: dict[str, object]) -> None:
        """Process a JSON-RPC request from Electron."""
        method = request.get("method")
        params = request.get("params", {}) or {}
        req_id = request.get("id")

        try:
            if method == "run_task":
                self._run_task(params, req_id)
            elif method == "cloud_model_response":
                self._handle_cloud_model_response(params)
            elif method == "confirmation_response":
                self._handle_confirmation_response(params)
            elif method == "cancel_task":
                self._handle_cancel_task(params)
            elif method == "stage_action":
                self._handle_stage_action(params, req_id)
            elif method == "software_feature":
                self._handle_software_feature(params, req_id)
            elif method == "interaction":
                self._handle_interaction(params, req_id)
            else:
                self._send_response(req_id, error=f"Unknown method: {method}")
        except Exception as exc:
            self.logger.error("Error handling request: %s", exc, exc_info=True)
            self._send_response(req_id, error=str(exc))

    def _emit_execution_plan(self, steps: list[str]) -> None:
        """Send a detected execution plan to Electron so it can show the banner."""
        self._notify("execution_plan", {
            "task_id": self.current_task_id,
            "steps": steps,
        })

    def _run_task(self, params: dict[str, object], req_id: object) -> None:
        self.current_task_id = str(params.get("task_id", ""))
        if isinstance(self.model, PlanDetectingModelProvider):
            self.model.reset_plan()
        workspace_root = str(params.get("workspace_root", "."))
        message = str(params.get("message", ""))

        # Enforce that the workspace root is an absolute path inside the user's
        # home directory. This is a second layer of defense on top of the path
        # checks in kyrozen/tools/_paths.py.
        root_path = Path(workspace_root).resolve()
        home_path = Path.home().resolve()
        if not root_path.is_absolute() or not str(root_path).startswith(str(home_path)):
            self._notify("task_result", {
                "task_id": self.current_task_id,
                "status": "failed",
                "result": {"answer": f"Invalid workspace root: {workspace_root}. It must be an absolute path under {home_path}."},
            })
            self._send_response(req_id, result={"status": "ok"})
            return

        # Override workspace root for this task so file tools operate locally.
        self.config.workspace_root = str(root_path)
        # Tool calls carry project_id. Point projects_dir at the selected
        # desktop workspace parent so config.project_dir(project_id) resolves
        # back to this exact directory instead of <workspace>/projects/<id>.
        self.config.projects_dir = str(root_path.parent)

        # ------------------------------------------------------------------
        # Route the task to the correct specialized agent (AgentRouter).
        # ------------------------------------------------------------------
        project_id = str(params.get("project_id", ""))
        requested_mode = str(params.get("mode", ""))
        stage = str(params.get("stage", ""))
        project_type = str(params.get("project_type", ""))

        state_dir = root_path / ".kyrozen"
        handoff_store = HandoffStore(state_dir / "handoff.json", project_id=project_id)
        handoff_tool = HandoffTool(handoff_store)
        registry = get_default_registry()
        registry.register(handoff_tool)

        # Stage gate (feature 3.2): keep the local gate in sync with the
        # server-reported lifecycle stage, scan deliverables, and push the gate
        # to the desktop UI so the panel always reflects real progress.
        self._sync_and_push_stage(root_path, stage, project_id)

        # Feature 3.4 (#5): re-show any confirmations that were pending when the
        # app last shut down. They are NOT auto-executed.
        self._restore_confirmations(root_path)

        self.router.log_path = state_dir / "routing_log.jsonl"
        agent, effective_registry, decision = self.router.route(
            requested_mode=requested_mode,
            stage=stage,
            project_type=project_type,
            user_message=message,
            capabilities=LocalCapabilities.detect(),
            registry=registry,
            agent_kwargs={
                "config": self.config,
                "model": self.model,
                "memory": InMemoryMemory(),
                "logger": self.logger,
                "confirmation_callback": self._request_confirmation,
            },
            task_id=self.current_task_id,
        )
        handoff_tool.mode = decision.mode
        self.agent = agent
        self._wrap_tool_execution(effective_registry)

        # Structured handoff: snapshot state when the active agent changes.
        previous_mode = handoff_store.last_mode
        if previous_mode and previous_mode != decision.mode:
            handoff_store.record_handoff(
                source_mode=previous_mode,
                source_agent=handoff_store.last_agent,
                target_mode=decision.mode,
                target_agent=decision.agent_name,
            )
        handoff_store.set_current_agent(decision.mode, decision.agent_name)

        # Report the routing decision: to the desktop UI and into the cloud
        # task record (task_step), so task history shows the exact agent.
        self._notify("agent_routed", {"task_id": self.current_task_id, **decision.to_dict()})
        self._notify("task_step", {
            "task_id": self.current_task_id,
            "step": {
                "description": f"路由到{decision.agent_display_name}（模式：{decision.mode}）",
                "status": "completed",
                "metadata": decision.to_dict(),
            },
        })
        if decision.degraded:
            self._notify("agent_degraded", {
                "task_id": self.current_task_id,
                "agent_display_name": decision.agent_display_name,
                "reason": decision.degraded_reason,
                "repair_steps": decision.repair_steps,
            })

        # Inject the persisted handoff context so a restarted or newly routed
        # agent never re-asks questions the user has already answered.
        agent_input = message
        context_block = handoff_store.context_block()
        if context_block:
            agent_input = f"{context_block}\n\n[用户消息]\n{message}"
        if decision.degraded:
            agent_input = (
                "[系统提示] 本地专用 Agent 初始化失败，当前处于只读降级模式：只能读取文件和检索信息，"
                "不能修改文件或执行命令。请先告知用户降级原因，再尽力用只读能力回答。\n"
                f"降级原因：{decision.degraded_reason}\n\n" + agent_input
            )

        self._notify("task_step", {
            "task_id": self.current_task_id,
            "step": {
                "description": "正在开始本地任务",
                "status": "running",
                "metadata": {"message": message, "agent": decision.agent_name, "mode": decision.mode},
            },
        })

        def execute() -> None:
            try:
                task = self.agent.run(agent_input, project_id=project_id)
                self.current_task = task
                self._cancel_task_timeout_timer()
                if not self._task_timed_out.is_set():
                    result = dict(task.result) if isinstance(task.result, dict) else {}
                    if task.result and not isinstance(task.result, dict):
                        result["answer"] = str(task.result)
                    if task.status == "failed" and not result.get("answer"):
                        errors = list(getattr(task, "errors", []) or [])
                        result["answer"] = errors[-1] if errors else "AI 服务暂时不可用，请稍后重试。"
                    self._notify("task_result", {
                        "task_id": self.current_task_id,
                        "status": task.status,
                        "result": result,
                        "steps": [step.to_dict() for step in task.steps],
                    })
            except Exception as exc:
                self._cancel_task_timeout_timer()
                traceback_str = traceback.format_exc()
                if not self._task_timed_out.is_set():
                    self._notify("task_result", {
                        "task_id": self.current_task_id,
                        "status": "failed",
                        "result": {"answer": f"Task failed: {exc}\n{traceback_str}"},
                    })

        self._task_timed_out.clear()
        timeout_seconds = int(params.get("timeout_seconds", self.DEFAULT_TASK_TIMEOUT_SECONDS))
        self._task_timeout_timer = threading.Timer(timeout_seconds, self._handle_task_timeout)
        self._task_timeout_timer.daemon = True
        self._task_timeout_timer.start()

        self._task_thread = threading.Thread(target=execute, daemon=True)
        self._task_thread.start()
        self._send_response(req_id, result={"status": "ok"})

    def _sync_and_push_stage(self, root_path: Path, stage: str, project_id: str) -> None:
        """Sync the local gate store with the server stage and push it to UI."""
        try:
            state_dir = root_path / ".kyrozen"
            store = StageGateStore(state_dir / "stagegate.json", project_id=project_id)
            if stage and stage in STAGES:
                store.current_stage = stage
                store.progress = compute_progress(store)
                store.save()
            gate = refresh_gate(store, str(root_path))
            self._push_stage(store, gate)
        except Exception as exc:
            self.logger.error("Stage gate sync failed: %s", exc, exc_info=True)

    def _push_stage(self, store: "StageGateStore", gate: "object" | None = None) -> None:
        """Emit a `stage_updated` event with the full gate snapshot."""
        try:
            from kyrozen.core.stagegate import GateStatus
            if gate is None or not isinstance(gate, GateStatus):
                gate = compute_gate(store)
            self._notify("stage_updated", {
                "task_id": self.current_task_id,
                "project_id": store.project_id,
                "stage": store.current_stage,
                "progress": store.progress,
                "gate": gate.to_dict(),
                "skips": [s.to_dict() for s in store.skips],
            })
        except Exception as exc:
            self.logger.error("Failed to push stage_updated: %s", exc, exc_info=True)

    def _handle_stage_action(self, params: dict[str, object], req_id: object) -> None:
        """Handle a stage-gate action requested from the desktop UI.

        actions:
          * 'refresh'        -- re-scan deliverables and return the gate
          * 'advance_normal' -- 继续当前阶段 (only if gate satisfied)
          * 'advance_risk'   -- 带风险推进 (skip missing required items)
          * 'return'         -- 返回上一阶段
        """
        action = str(params.get("action", "refresh"))
        workspace_root = str(params.get("workspace_root", "."))
        project_id = str(params.get("project_id", ""))
        stage = str(params.get("stage", ""))
        root_path = Path(workspace_root).resolve()
        try:
            store = StageGateStore(root_path / ".kyrozen" / "stagegate.json", project_id=project_id)
            if stage and stage in STAGES:
                store.current_stage = stage
            # Always re-scan so the gate reflects the latest workspace state
            # before any transition decision.
            gate = refresh_gate(store, str(root_path))
            if action == "advance_normal":
                result = advance(store, "normal")
            elif action == "advance_risk":
                raw_details = params.get("risk_details") or {}
                result = advance(store, "risk", raw_details if isinstance(raw_details, dict) else {})
            elif action == "return":
                result = advance(store, "return")
            else:
                result = {"ok": True, **get_status(store, gate)}
            # A transition changes which deliverables are relevant. Re-scan
            # the newly active stage before responding/pushing; otherwise the
            # UI briefly (and sometimes permanently) reports files such as
            # docs/TECH_DESIGN.md as missing until a manual refresh.
            if action in {"advance_normal", "advance_risk", "return"} and result.get("ok"):
                gate = refresh_gate(store, str(root_path))
                result = {**result, **get_status(store, gate)}
            self._send_response(req_id, result=result)
            # Push the updated gate to the UI regardless of the action.
            self._push_stage(store, gate)
        except Exception as exc:
            self.logger.error("stage_action failed: %s", exc, exc_info=True)
            self._send_response(req_id, error=str(exc))

    def _handle_software_feature(self, params: dict[str, object], req_id: object) -> None:
        """Handle a 3.3 software generate / run / repair / noncoding request.

        Triggered from the desktop UI (kyzen:software-feature). The engine is
        deterministic, so it works without an LLM and persists results to
        <workspace>/.kyrozen/software_feature.json for the UI panel.
        """
        action = str(params.get("action", "generate"))
        workspace_root = str(params.get("workspace_root", "."))
        root_path = Path(workspace_root).resolve()
        if action == "load":
            saved = featuregen_mod.load_software_feature(root_path)
            if saved:
                spec_data = saved.get("spec", {})
                run_data = dict(saved.get("run", {}))
                payload = {
                    "action": "run",
                    "app_type": spec_data.get("application_type", "web_app"),
                    "run": run_data,
                    "feature_records": saved.get("feature_records", run_data.get("feature_records", [])),
                    "preview_url": run_data.get("preview_url", ""),
                    "command": run_data.get("command", ""),
                    "artifact_path": run_data.get("artifact_path", ""),
                    "restored": True,
                }
                self._send_response(req_id, result=payload)
                self._notify("software_feature", payload)
            else:
                self._send_response(req_id, result={"action": "load", "restored": False})
            return
        op_log = operation_mod.OperationLog(root_path)
        op_id = op_log.start(f"software.{action}", input_summary={
            "generate": "生成并写入软件工作区", "run": "安装、构建、测试并启动预览",
            "repair": "读取失败并自动修复", "noncoding": "生成结构化非代码交付物",
        }.get(action, action))
        try:
            if action == "generate":
                prd = params.get("prd") or {}
                if isinstance(prd, str):
                    try:
                        prd = json.loads(prd)
                    except Exception:
                        prd = {}
                spec = featuregen_mod.generate_project_spec(
                    prd,
                    app_type=str(params.get("app_type") or "web_app"),
                    app_name=params.get("app_name"),
                    description=str(params.get("description") or ""),
                )
                result = featuregen_mod.scaffold_project(spec, root_path)
                payload = {
                    "action": "generate",
                    "app_type": spec.application_type,
                    "files": result.files,
                    "manifest_path": result.manifest_path,
                    "feature_slugs": spec.feature_slugs(),
                }
            elif action == "run":
                manifest = featuregen_mod.load_manifest(root_path)
                spec = featuregen_mod.SoftwareProjectSpec.from_dict(manifest.get("spec", {})) if manifest else featuregen_mod.generate_project_spec(app_type="web_app")
                port = int(params.get("port") or featuregen_mod.DEFAULT_PORT)
                runner = featuregen_mod.BuildRunner()
                run = runner.run_all(root_path, port=port)
                records = featuregen_mod.build_feature_records(spec, run)
                run.feature_records = records
                saved = featuregen_mod.save_software_feature(root_path, spec, run, feature_records=records)
                gate_store = StageGateStore(root_path / ".kyrozen" / "stagegate.json", project_id=str(params.get("project_id") or ""))
                if gate_store.current_stage == "development":
                    gate_store.record_verification("build_passes", run.overall_success, detail="真实安装、构建、测试与核心流程通过" if run.overall_success else "运行或测试失败")
                elif gate_store.current_stage == "testing":
                    gate_store.record_verification("tests_pass", run.overall_success, detail="真实测试与核心流程通过" if run.overall_success else "测试失败")
                gate = refresh_gate(gate_store, str(root_path))
                self._push_stage(gate_store, gate)
                payload = {
                    "action": "run",
                    "run": run.to_dict(),
                    "feature_records": [r.to_dict() for r in records],
                    "preview_url": run.preview_url,
                    "command": run.command,
                    "artifact_path": run.artifact_path,
                    "saved_path": str(saved),
                }
            elif action == "repair":
                manifest = featuregen_mod.load_manifest(root_path)
                spec = featuregen_mod.SoftwareProjectSpec.from_dict(manifest.get("spec", {})) if manifest else featuregen_mod.generate_project_spec(app_type="web_app")
                command = str(params.get("command") or f"{sys.executable} -m py_compile app.py tests/*.py")
                max_attempts = int(params.get("max_attempts") or 3)
                outcome = featuregen_mod.run_with_repair(featuregen_mod.CommandExecutor(), command, root_path, file_tasks=spec.file_tasks, max_attempts=max_attempts)
                run = featuregen_mod.BuildRunner().run_all(root_path, port=featuregen_mod.DEFAULT_PORT)
                records = featuregen_mod.build_feature_records(spec, run)
                run.feature_records = records
                saved = featuregen_mod.save_software_feature(root_path, spec, run, feature_records=records)
                gate_store = StageGateStore(root_path / ".kyrozen" / "stagegate.json", project_id=str(params.get("project_id") or ""))
                if gate_store.current_stage == "development":
                    gate_store.record_verification("build_passes", run.overall_success, detail="修复后真实构建与测试通过" if run.overall_success else "修复后仍未通过")
                elif gate_store.current_stage == "testing":
                    gate_store.record_verification("tests_pass", run.overall_success, detail="修复后真实测试通过" if run.overall_success else "修复后测试仍失败")
                gate = refresh_gate(gate_store, str(root_path))
                self._push_stage(gate_store, gate)
                payload = {
                    "action": "repair",
                    "repair": outcome.to_dict(),
                    "feature_records": [r.to_dict() for r in records],
                    "saved_path": str(saved),
                }
            elif action == "noncoding":
                dtype = str(params.get("deliverable_type") or "")
                title = str(params.get("title") or "未命名交付物")
                fields = params.get("fields") or {}
                if isinstance(fields, str):
                    try:
                        fields = json.loads(fields)
                    except Exception:
                        fields = {}
                res = deliverable_mod.build_deliverable(dtype, title, fields, root_path)
                payload = {
                    "action": "noncoding",
                    "deliverable_type": res.deliverable_type,
                    "title": res.title,
                    "file": res.file,
                    "markdown": res.markdown,
                }
            else:
                self._send_response(req_id, error=f"Unknown software_feature action: {action}")
                return
            self._send_response(req_id, result=payload)
            self._notify("software_feature", payload)
            op_log.end(op_id, output_summary={
                "generate": f"写入 {len(payload.get('files', []))} 个文件",
                "run": "运行与测试通过" if payload.get("run", {}).get("overall_success") else "运行或测试失败",
                "repair": f"完成 {payload.get('repair', {}).get('attempts', 0)} 次修复尝试",
                "noncoding": f"已保存 {payload.get('file', '')}",
            }.get(action, "操作完成"), status="success")
            self._notify("interaction", {"action": "op_list", "records": op_log.list()})
        except Exception as exc:
            op_log.end(op_id, status="failed", error_reason=str(exc))
            self._notify("interaction", {"action": "op_list", "records": op_log.list()})
            self.logger.error("software_feature failed: %s", exc, exc_info=True)
            self._send_response(req_id, error=str(exc))

    def _handle_interaction(self, params: dict[str, object], req_id: object) -> None:
        """Handle a 3.4 interaction request (attachments / status / logs / confirmations).

        Triggered from the desktop UI (kyzen:interaction). All engines persist to
        <workspace>/.kyrozen/ so the UI panels and restart-restore work.
        """
        action = str(params.get("action", ""))
        workspace_root = str(params.get("workspace_root", "."))
        root_path = Path(workspace_root).resolve()
        try:
            if action == "attach":
                path = str(params.get("path") or "")
                op_log = operation_mod.OperationLog(root_path)
                op_id = op_log.start("attachment.add", input_summary=f"添加附件 {Path(path).name}")
                try:
                    manager = attachments_mod.AttachmentsManager(
                        root_path,
                        image_analyzer=_make_ai_image_analyzer(),
                        video_analyzer=attachments_mod.VideoAnalyzer(asr_fn=_make_asr_fn()),
                    )
                    attachment = manager.add(path)
                    payload = {"action": "attach", "attachment": attachment.to_dict()}
                    op_log.end(op_id, output_summary=f"已分析 {attachment.filename}", status="success")
                except attachments_mod.AttachmentError as exc:
                    payload = {"action": "attach", "error": exc.args[0] if exc.args else str(exc), "reason": exc.reason}
                    op_log.end(op_id, status="failed", error_reason=str(exc))
                self._notify("interaction", {"action": "op_list", "records": op_log.list()})
            elif action == "delete_attachment":
                manager = attachments_mod.AttachmentsManager(root_path)
                ok = manager.delete(str(params.get("attachment_id") or ""))
                payload = {"action": "delete_attachment", "deleted": ok}
            elif action == "attach_list":
                manager = attachments_mod.AttachmentsManager(root_path)
                payload = {"action": "attach_list", "attachments": [a.to_dict() for a in manager.list()]}
            elif action == "status_set":
                mgr = status_mod.StatusManager(root_path)
                try:
                    payload = {"action": "status_set", "status": mgr.set(str(params.get("state")), detail=params.get("detail"))}
                except ValueError as exc:
                    payload = {"action": "status_set", "error": str(exc)}
            elif action == "status_get":
                payload = {"action": "status_get", "status": status_mod.StatusManager(root_path).current()}
            elif action == "op_start":
                log = operation_mod.OperationLog(root_path)
                payload = {"action": "op_start", "record_id": log.start(str(params.get("action")), input_summary=str(params.get("input_summary") or ""))}
            elif action == "op_end":
                log = operation_mod.OperationLog(root_path)
                log.end(str(params.get("record_id")), output_summary=str(params.get("output_summary") or ""),
                        status=str(params.get("status") or "success"), error_reason=str(params.get("error_reason") or ""))
                payload = {"action": "op_end", "ok": True}
            elif action == "op_list":
                log = operation_mod.OperationLog(root_path)
                limit = params.get("limit")
                payload = {"action": "op_list", "records": log.list(limit=int(limit) if limit is not None else None)}
            elif action == "diagnostic":
                kind = str(params.get("kind") or "")
                raw = params.get("payload")
                try:
                    payload_obj = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    payload_obj = raw
                try:
                    operation_mod.DiagnosticsLog(root_path).append(kind, payload_obj)
                    payload = {"action": "diagnostic", "ok": True}
                except ValueError as exc:
                    payload = {"action": "diagnostic", "error": str(exc)}
            elif action == "confirm_create":
                store = confirmation_mod.ConfirmationStore(root_path)
                conf = store.create(
                    operation_type=str(params.get("operation_type") or ""),
                    action_label=str(params.get("action_label") or params.get("operation_type") or ""),
                    params=(json.loads(params["params"]) if isinstance(params.get("params"), str) else (params.get("params") or {})),
                    reason=str(params.get("reason") or ""),
                )
                payload = {"action": "confirm_create", "confirmation": conf.to_dict()}
            elif action == "confirm_resolve":
                store = confirmation_mod.ConfirmationStore(root_path)
                try:
                    conf = store.resolve(str(params.get("confirmation_id")), str(params.get("choice")))
                except ValueError as exc:
                    conf = None
                    payload = {"action": "confirm_resolve", "error": str(exc)}
                if conf is not None:
                    payload = {"action": "confirm_resolve", "confirmation": conf.to_dict()}
            elif action == "confirm_pending":
                store = confirmation_mod.ConfirmationStore(root_path)
                payload = {"action": "confirm_pending", "pending": [c.to_dict() for c in store.pending()]}
            elif action == "confirm_is_trusted":
                store = confirmation_mod.ConfirmationStore(root_path)
                payload = {"action": "confirm_is_trusted", "trusted": store.is_trusted(str(params.get("operation_type") or ""))}
            else:
                self._send_response(req_id, error=f"Unknown interaction action: {action}")
                return
            self._send_response(req_id, result=payload)
            self._notify("interaction", payload)
        except Exception as exc:
            self.logger.error("interaction failed: %s", exc, exc_info=True)
            self._send_response(req_id, error=str(exc))

    def _cancel_task_timeout_timer(self) -> None:
        """Stop the task timeout timer if it is still running."""
        timer = self._task_timeout_timer
        if timer is not None:
            timer.cancel()
            self._task_timeout_timer = None

    def _handle_task_timeout(self) -> None:
        """Mark the current task as timed out and cancel the agent."""
        self._task_timed_out.set()
        self.logger.warning("Task %s timed out", self.current_task_id)
        if self.agent:
            self.agent.cancel()
        if self.current_task and self.current_task.status == "running":
            self.current_task.update_status("failed")
        self._notify("task_result", {
            "task_id": self.current_task_id,
            "status": "failed",
            "result": {"answer": "任务执行超时，已自动终止。"},
        })

    def _workspace_path(self) -> "Path | None":
        ws = getattr(self.config, "workspace_root", None)
        if not ws or ws in (".", ""):
            return None
        p = Path(ws)
        if not p.is_absolute():
            return None
        return p

    @staticmethod
    def _status_for_tool(tool_name: str, action: str) -> "status_mod.StatusState":
        if tool_name in {"read_file", "file_read", "list_dir", "find_files"}:
            return status_mod.StatusState.READING
        if tool_name in {"write_file", "file_write", "edit_file"}:
            return status_mod.StatusState.EDITING
        if tool_name in {"web_search", "search_github"} or tool_name.startswith("github"):
            return status_mod.StatusState.SEARCHING
        if tool_name.startswith("git") or tool_name == "git":
            return status_mod.StatusState.RUNNING
        return status_mod.StatusState.RUNNING

    def _wrap_tool_execution(self, tools: object) -> None:
        """Report concise tool activity, keep the status bar and operation log,
        and route raw tool JSON to the diagnostics sink (requirements #2, #3, #6)."""
        original_execute = getattr(tools, "execute")

        def wrapped(tool_name: str, action: str, parameters: dict[str, object]) -> object:
            description = self._describe_tool_operation(tool_name, action, parameters)
            ws = self._workspace_path()
            op_id: str | None = None
            if ws is not None:
                try:
                    op_id = operation_mod.OperationLog(ws).start(description, input_summary=description)
                except Exception:
                    op_id = None
                try:
                    st = self._status_for_tool(tool_name, action)
                    status_mod.StatusManager(ws).set(st)
                    self._notify("status_updated", {"state": st.value, "detail": description})
                except Exception:
                    pass

            self._notify("task_operation", {
                "task_id": self.current_task_id,
                "description": description,
                "status": "running",
            })
            try:
                result = original_execute(tool_name, action, parameters)
            except Exception:
                # Surface a retry, then retry once for non-destructive tools.
                retryable = tool_name not in ("terminal",) and not tool_name.startswith("git")
                if retryable and ws is not None:
                    try:
                        status_mod.StatusManager(ws).set(status_mod.StatusState.RETRYING)
                        self._notify("status_updated", {"state": "retrying", "detail": description})
                        result = original_execute(tool_name, action, parameters)
                    except Exception:
                        self._finalize_op(ws, op_id, description, False, "工具执行异常")
                        self._notify("task_operation", {
                            "task_id": self.current_task_id,
                            "description": description,
                            "status": "failed",
                        })
                        raise
                else:
                    self._finalize_op(ws, op_id, description, False, "工具执行异常")
                    self._notify("task_operation", {
                        "task_id": self.current_task_id,
                        "description": description,
                        "status": "failed",
                    })
                    raise

            # Requirement #6: raw tool JSON goes ONLY to the diagnostics sink.
            if ws is not None:
                self._record_diagnostic(ws, tool_name, action, parameters, result)

            if tool_name == "terminal" and action == "execute":
                output = ""
                if hasattr(result, "data") and result.data:
                    output = str(result.data.get("output", "")) + str(result.data.get("error", ""))
                url = self._extract_local_url(output)
                if url:
                    self._notify("open_preview", {"url": url})

            succeeded = bool(getattr(result, "success", True))
            self._finalize_op(ws, op_id, description, succeeded, "" if succeeded else "工具返回失败")
            self._notify("task_operation", {
                "task_id": self.current_task_id,
                "description": description,
                "status": "completed" if succeeded else "failed",
            })
            if ws is not None:
                try:
                    status_mod.StatusManager(ws).clear()
                    self._notify("status_updated", {"state": None, "detail": None})
                except Exception:
                    pass
            return result

        setattr(tools, "execute", wrapped)

    def _finalize_op(
        self,
        ws: "Path | None",
        op_id: str | None,
        description: str,
        succeeded: bool,
        error_reason: str,
    ) -> None:
        if ws is None or not op_id:
            return
        try:
            operation_mod.OperationLog(ws).end(
                op_id,
                output_summary=description,
                status="success" if succeeded else "failed",
                error_reason=error_reason,
            )
            # Requirement #3: keep the collapsible operation record above the
            # final answer in sync. Push the refreshed list after each op ends.
            records = operation_mod.OperationLog(ws).list(limit=None)
            self._notify(
                "interaction",
                {"action": "op_list", "records": [r.to_dict() for r in records]},
            )
        except Exception:
            pass

    def _record_diagnostic(
        self,
        ws: "Path",
        tool_name: str,
        action: str,
        parameters: dict[str, object],
        result: object,
    ) -> None:
        try:
            payload = {
                "tool": tool_name,
                "action": action,
                "parameters": parameters,
                "result": getattr(result, "data", None),
            }
            operation_mod.DiagnosticsLog(ws).append("tool_json", payload)
        except Exception:
            pass

    @staticmethod
    def _describe_tool_operation(tool_name: str, action: str, parameters: dict[str, object]) -> str:
        path = str(parameters.get("path") or parameters.get("file_path") or parameters.get("directory") or "").strip()
        command = str(parameters.get("command") or "").strip()
        if tool_name in {"read_file", "file_read"}:
            return f"Reading file: {path or 'project file'}"
        if tool_name in {"write_file", "file_write", "edit_file"}:
            return f"Editing file: {path or 'project file'}"
        if tool_name in {"list_dir", "find_files"}:
            return f"Inspecting files: {path or 'project workspace'}"
        if tool_name == "terminal":
            summary = command.splitlines()[0][:80] if command else action
            return f"Running command: {summary}"
        if tool_name in {"web_search", "search_github"}:
            return f"Researching: {str(parameters.get('query') or 'market information')[:80]}"
        if tool_name.startswith("git") or tool_name == "git":
            return f"Updating Git repository: {action}"
        return f"Using {tool_name}: {action}"

    def _extract_local_url(self, text: str) -> str | None:
        """Look for common local development server URLs in command output."""
        import re
        patterns = [
            r"(http://localhost:\d+)",
            r"(http://127\.0\.0\.1:\d+)",
            r"Local:\s+(http://\S+)",
            r"Network:\s+(http://\S+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _request_confirmation(
        self,
        *,
        task: Task,
        tool: str,
        action: str,
        parameters: dict[str, object],
        reason: str,
    ) -> bool:
        """Called by BaseAgent when a tool requires user confirmation.

        Sends a request to Electron and blocks until the user responds. The
        pending confirmation is also persisted to the durable store so it can be
        restored after an app restart (requirement #5).
        """
        confirmation_id = f"conf_{task.id}_{tool}_{action}_{int(time.time() * 1000)}"
        pending = PendingConfirmation()
        operation_type = f"{tool}.{action}"
        with self._lock:
            self._pending_confirmations[confirmation_id] = pending

        # Persist to the durable store so the card survives a restart.
        ws = self._workspace_path()
        if ws is not None:
            try:
                conf = confirmation_mod.ConfirmationStore(ws).create(
                    operation_type=operation_type,
                    action_label=f"{tool}.{action}",
                    params=dict(parameters) if isinstance(parameters, dict) else {},
                    reason=reason or "",
                )
                pending.store_id = conf.id
            except Exception:
                pending.store_id = None

        self._notify("request_confirmation", {
            "task_id": task.id,
            "confirmation_id": confirmation_id,
            "store_id": pending.store_id,
            "operation_type": operation_type,
            "tool": tool,
            "action": action,
            "parameters": parameters,
            "reason": reason,
            "choices": ["allow_once", "trust_project", "reject"],
        })

        # Wait for Electron to respond (with a generous timeout).
        pending.event.wait(timeout=300)

        with self._lock:
            self._pending_confirmations.pop(confirmation_id, None)

        # Persist the resolution into the durable store.
        if ws is not None and pending.store_id:
            try:
                choice = (
                    "trust_project" if pending.trust_for_session
                    else "allow_once" if pending.result else "reject"
                )
                confirmation_mod.ConfirmationStore(ws).resolve(pending.store_id, choice)
            except Exception:
                pass

        if pending.trust_for_session:
            return {"confirmed": pending.result, "trust_for_session": True}
        return pending.result

    def _handle_confirmation_response(self, params: dict[str, object]) -> None:
        confirmation_id = str(params.get("confirmation_id", ""))
        confirmed = bool(params.get("confirmed", False))
        trust_for_session = bool(params.get("trust_for_session", False))
        store_id = params.get("store_id")
        with self._lock:
            pending = self._pending_confirmations.get(confirmation_id)
            if pending is not None:
                pending.result = confirmed
                pending.trust_for_session = trust_for_session
                pending.event.set()
        # Persist into the durable store too (covers restored cards resolved
        # after a restart, where there is no live in-memory pending object).
        ws = self._workspace_path()
        if ws is not None:
            try:
                store = confirmation_mod.ConfirmationStore(ws)
                choice = (
                    "trust_project" if trust_for_session
                    else "allow_once" if confirmed else "reject"
                )
                if store_id and store.status_of(str(store_id)) is not None:
                    store.resolve(str(store_id), choice)
                elif store.status_of(confirmation_id) is not None:
                    store.resolve(confirmation_id, choice)
            except Exception:
                pass

    def _restore_confirmations(self, root_path: Path) -> None:
        """Re-show pending confirmations after an app restart (requirement #5).

        The operations they gate are NOT auto-executed -- the user must decide
        again. This only re-emits the cards to the desktop UI.
        """
        try:
            store = confirmation_mod.ConfirmationStore(root_path)
            for conf in store.restore():
                op_parts = conf.operation_type.split(".", 1)
                self._notify("request_confirmation", {
                    "task_id": self.current_task_id,
                    "confirmation_id": conf.id,
                    "store_id": conf.id,
                    "operation_type": conf.operation_type,
                    "tool": op_parts[0] if op_parts else conf.operation_type,
                    "action": op_parts[1] if len(op_parts) > 1 else "",
                    "parameters": conf.params,
                    "reason": conf.reason,
                    "choices": ["allow_once", "trust_project", "reject"],
                    "restored": True,
                })
        except Exception as exc:
            self.logger.error("restore confirmations failed: %s", exc, exc_info=True)

    def _handle_cloud_model_response(self, params: dict[str, object]) -> None:
        if self.model is None:
            return
        self.model.handle_response(params)

    def _handle_cancel_task(self, params: dict[str, object]) -> None:
        task_id = str(params.get("task_id", ""))
        self.logger.info("Received cancel request for task %s", task_id)
        self._cancel_task_timeout_timer()
        if self.agent:
            self.agent.cancel()
        if self.current_task and self.current_task.status == "running":
            self.current_task.update_status("cancelled")
            self._notify("task_result", {
                "task_id": self.current_task_id,
                "status": "cancelled",
                "result": {"answer": "任务已被用户取消"},
            })

    def _notify(self, method: str, params: dict[str, object]) -> None:
        if self.send_message is None:
            return
        self.send_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _send_response(self, req_id: object, result: object = None, error: str | None = None) -> None:
        if self.send_message is None or req_id is None:
            return
        payload: dict[str, object] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            payload["error"] = {"message": error}
        else:
            payload["result"] = result or {}
        self.send_message(payload)


def main() -> None:
    runtime = DesktopAgentRuntime()

    def send_message(message: dict[str, object]) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    runtime.set_send_message(send_message)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            send_message({"jsonrpc": "2.0", "error": {"message": "Invalid JSON"}})
            continue
        runtime.handle_request(request)


if __name__ == "__main__":
    main()
