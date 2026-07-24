"""Python Agent Runtime entry point for Kyrozen Desktop Client.

Reads JSON-RPC requests from stdin and writes responses to stdout.
Communicates with the Electron main process via stdio.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

# Make the repository root importable so we can reuse kyrozen core modules.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kyrozen.config import get_config
from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import Task
from kyrozen.desktop import CloudProxyModelProvider
from kyrozen.logs import get_logger
from kyrozen.memory import InMemoryMemory
from kyrozen.tools import get_default_registry


class PendingConfirmation:
    """Thread-safe container for an outstanding user confirmation."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: bool = False


class DesktopAgentRuntime:
    """Minimal local agent runtime that talks to Electron over stdio JSON-RPC."""

    def __init__(self) -> None:
        self.config = get_config()
        self.logger = get_logger(self.config.log_level)
        self.send_message: callable | None = None
        self.model: CloudProxyModelProvider | None = None
        self.agent: BaseAgent | None = None
        self.current_task_id: str | None = None
        self.current_task: Task | None = None
        self._pending_confirmations: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()
        self._task_thread: threading.Thread | None = None

    def set_send_message(self, send_message: callable) -> None:
        """Bind the function used to send JSON-RPC messages to Electron."""
        self.send_message = send_message
        self.model = CloudProxyModelProvider(send_message=send_message)
        self.agent = BaseAgent(
            config=self.config,
            model=self.model,
            tools=get_default_registry(),
            memory=InMemoryMemory(),
            logger=self.logger,
            confirmation_callback=self._request_confirmation,
        )

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
            else:
                self._send_response(req_id, error=f"Unknown method: {method}")
        except Exception as exc:
            self.logger.error("Error handling request: %s", exc, exc_info=True)
            self._send_response(req_id, error=str(exc))

    def _run_task(self, params: dict[str, object], req_id: object) -> None:
        self.current_task_id = str(params.get("task_id", ""))
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

        self._notify("task_step", {
            "task_id": self.current_task_id,
            "step": {
                "description": "Starting local task execution",
                "status": "running",
                "metadata": {"message": message},
            },
        })

        def execute() -> None:
            try:
                task = self.agent.run(message, project_id=str(params.get("project_id", "")))
                self.current_task = task
                self._notify("task_result", {
                    "task_id": task.id,
                    "status": task.status,
                    "result": task.result or {},
                    "steps": [step.to_dict() for step in task.steps],
                })
            except Exception as exc:
                traceback_str = traceback.format_exc()
                self._notify("task_result", {
                    "task_id": self.current_task_id,
                    "status": "failed",
                    "result": {"answer": f"Task failed: {exc}\n{traceback_str}"},
                })

        self._task_thread = threading.Thread(target=execute, daemon=True)
        self._task_thread.start()
        self._send_response(req_id, result={"status": "ok"})

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

        Sends a request to Electron and blocks until the user responds.
        """
        confirmation_id = f"conf_{task.id}_{tool}_{action}_{int(time.time() * 1000)}"
        pending = PendingConfirmation()
        with self._lock:
            self._pending_confirmations[confirmation_id] = pending

        self._notify("request_confirmation", {
            "task_id": task.id,
            "confirmation_id": confirmation_id,
            "tool": tool,
            "action": action,
            "parameters": parameters,
            "reason": reason,
        })

        # Wait for Electron to respond (with a generous timeout).
        pending.event.wait(timeout=300)

        with self._lock:
            self._pending_confirmations.pop(confirmation_id, None)
        return pending.result

    def _handle_confirmation_response(self, params: dict[str, object]) -> None:
        confirmation_id = str(params.get("confirmation_id", ""))
        confirmed = bool(params.get("confirmed", False))
        with self._lock:
            pending = self._pending_confirmations.get(confirmation_id)
            if pending is None:
                return
            pending.result = confirmed
            pending.event.set()

    def _handle_cloud_model_response(self, params: dict[str, object]) -> None:
        if self.model is None:
            return
        self.model.handle_response(params)

    def _handle_cancel_task(self, params: dict[str, object]) -> None:
        task_id = str(params.get("task_id", ""))
        self.logger.info("Received cancel request for task %s", task_id)
        if self.agent:
            self.agent.cancel()
        if self.current_task and self.current_task.status == "running":
            self.current_task.update_status("cancelled")
            self._notify("task_result", {
                "task_id": self.current_task.id,
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
