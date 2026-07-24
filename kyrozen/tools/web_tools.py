"""Web capture and local-app testing tools for Kyrozen.

These tools let the agent test locally running web applications and store
snapshots of web pages captured by the browser extension.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Tool, ToolParameter, ToolResult, ToolSchema


class WebTestTool(Tool):
    """Smoke-test a locally running web application."""

    name = "web_test"
    description = (
        "Smoke-test a local or remote web application. Performs an HTTP GET, "
        "checks the status code, extracts the page title, and optionally looks "
        "for expected text."
    )
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "test_local_app": [
                ToolParameter(
                    name="url",
                    param_type="string",
                    description="Full URL of the local web app to test (e.g. http://localhost:5173)",
                    required=True,
                ),
                ToolParameter(
                    name="expected_text",
                    param_type="string",
                    description="Optional text that should appear in the response body",
                    required=False,
                ),
            ],
        },
    )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if action != "test_local_app":
            return ToolResult(success=False, data=None, error=f"Unknown action: {action}")

        url = parameters.get("url", "")
        expected_text = parameters.get("expected_text", "")

        try:
            import requests
        except ImportError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=f"requests is not installed: {exc}",
            )

        try:
            response = requests.get(url, timeout=30)
            title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""

            data = {
                "url": url,
                "status_code": response.status_code,
                "title": title,
                "content_length": len(response.text),
                "expected_text_found": bool(expected_text) and expected_text in response.text,
            }

            if response.status_code >= 400:
                return ToolResult(
                    success=False,
                    data=data,
                    error=f"HTTP {response.status_code}",
                )
            if expected_text and expected_text not in response.text:
                return ToolResult(
                    success=False,
                    data=data,
                    error=f"Expected text not found: {expected_text}",
                )

            return ToolResult(success=True, data=data)
        except Exception as exc:
            return ToolResult(success=False, data=None, error=f"Request failed: {exc}")


class WebCaptureTool(Tool):
    """Store a web page snapshot captured by the browser extension."""

    name = "web_capture"
    description = (
        "Store a web page snapshot (URL, title, and text content) into the "
        "project memory. Usually called by the browser extension, not directly "
        "by the agent."
    )
    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "save": [
                ToolParameter(
                    name="project_id",
                    param_type="string",
                    description="Project ID to associate the capture with",
                    required=True,
                ),
                ToolParameter(
                    name="url",
                    param_type="string",
                    description="URL of the captured page",
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    param_type="string",
                    description="Page title",
                    required=False,
                ),
                ToolParameter(
                    name="content",
                    param_type="string",
                    description="Plain-text content extracted from the page",
                    required=False,
                ),
            ],
        },
    )

    def __init__(self, project_manager: Any = None) -> None:
        self.project_manager = project_manager

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if action != "save":
            return ToolResult(success=False, data=None, error=f"Unknown action: {action}")

        project_id = parameters.get("project_id", "")
        url = parameters.get("url", "")
        title = parameters.get("title", "")
        content = parameters.get("content", "")

        if not project_id or not url:
            return ToolResult(success=False, data=None, error="Missing project_id or url")

        try:
            from kyrozen.memory import JsonFileMemory, ProjectMemory
            from kyrozen.config import get_config

            config = get_config()
            backend = JsonFileMemory(config.project_memory_path(project_id))
            memory = ProjectMemory(project_id, backend)
            record = memory.save(
                category="web_capture",
                content=content or title or url,
                url=url,
                title=title,
            )
            return ToolResult(success=True, data={"record_id": record.id})
        except Exception as exc:
            return ToolResult(success=False, data=None, error=f"Failed to save web capture: {exc}")
