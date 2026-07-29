"""Packaged Python Agent startup smoke test (P0-01).

This test launches the desktop Python Agent exactly as the Electron shell does
(stdin/stdout JSON-RPC over a subprocess) and verifies that:

1. The module imports WITHOUT raising (the historical bug was an import of a
   non-existent ``stage_advance`` symbol that crashed the packaged Agent on
   startup, taking down routing, stage gate, software generation, attachments,
   confirmation and local execution with it).
2. The Agent emits a ``ready`` notification on startup so the desktop UI can
   stop showing an undefined loading state.
3. A ``stage_action`` request is handled and a valid response is returned while
   the process stays alive (it did not crash mid-request).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "desktop" / "python_agent" / "main.py"


def _read_until_id(proc: "subprocess.Popen[str]", req_id: str, timeout: float = 30.0) -> dict:
    """Read stdout lines until we find a response carrying ``req_id``.

    Ignores the startup ``ready`` notification (which has no id) and any other
    notifications. Raises AssertionError on EOF / timeout (process crashed).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(
                f"Agent process exited early (code {proc.poll()}). stderr:\n{stderr}"
            )
        line = proc.stdout.readline()
        if not line:
            # EOF without our response -> the process died.
            raise AssertionError("Agent closed stdout before answering the request.")
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == req_id:
            return msg
        # Otherwise it's a notification (e.g. 'ready'); keep reading.
    raise AssertionError("Timed out waiting for Agent response.")


@pytest.mark.parametrize("stage", ["problem_discovery", "development"])
def test_packaged_agent_starts_and_responds(stage: str):
    assert MAIN_PY.exists(), f"missing agent entrypoint: {MAIN_PY}"

    env = dict(os.environ)
    # Run from repo root so get_config() can load .env like production does.
    proc = subprocess.Popen(
        [sys.executable, str(MAIN_PY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        bufsize=1,
    )

    try:
        # The 'ready' notification should arrive first.
        ready_line = proc.stdout.readline()
        assert ready_line.strip(), "Agent produced no startup output (likely crashed)."
        ready = json.loads(ready_line)
        assert ready.get("method") == "ready", f"expected 'ready' notification, got: {ready}"
        assert ready["params"].get("status") == "ready"

        # Now drive a real stage_action request (no backend / model needed).
        workspace = tempfile.mkdtemp(prefix="kyrozen_agent_smoke_")
        req = {
            "jsonrpc": "2.0",
            "id": "smoke-1",
            "method": "stage_action",
            "params": {
                "action": "refresh",
                "workspace_root": workspace,
                "project_id": "proj_smoke",
                "stage": stage,
            },
        }
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()

        resp = _read_until_id(proc, "smoke-1")
        assert resp.get("error") is None, f"stage_action returned error: {resp.get('error')}"
        result = resp.get("result", {})
        assert result.get("stage") == stage, f"unexpected stage in result: {result}"
        # Progress must be an int (real status, not a crash placeholder).
        assert isinstance(result.get("progress"), int)

        # Process must still be alive after a successful request.
        assert proc.poll() is None, "Agent crashed after handling a request."
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
