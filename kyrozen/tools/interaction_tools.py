"""Tool exposing the 3.4 interaction engine: attachments, status, operation
logs, diagnostics and confirmations.

All state is persisted to ``<workspace>/.kyrozen/`` so it survives reloads and
can be rendered by the desktop client (attachments panel, status bar, collapsible
operation log, confirmation cards).
"""

from __future__ import annotations

from typing import Any

from kyrozen.core import attachments as att_mod
from kyrozen.core import confirmation as conf_mod
from kyrozen.core import operation_log as ol_mod
from kyrozen.core import status_state as ss_mod
from kyrozen.tools.base import Tool, ToolParameter, ToolResult, ToolSchema


def _ws(params: dict[str, Any]) -> str:
    ws = str(params.get("workspace_root") or "")
    if not ws:
        raise ValueError("workspace_root is required")
    return ws


def _parse_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return __import__("json").loads(value)
        except Exception:
            return default
    return default


class InteractionTool(Tool):
    name = "interaction"
    description = "附件、状态、操作记录、诊断与确认：管理图片/视频附件、Agent 状态、操作日志、诊断记录与待确认操作。"

    schema = ToolSchema(
        name=name,
        description=description,
        actions={
            "attach": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("path", "string", "附件文件路径", required=True),
            ],
            "delete_attachment": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("attachment_id", "string", "附件 ID", required=True),
            ],
            "attach_list": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
            ],
            "status_set": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("state", "string", "reading|editing|running|searching|waiting|retrying", required=True),
                ToolParameter("detail", "string", "状态说明（可选）", required=False),
            ],
            "status_get": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
            ],
            "op_start": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("action", "string", "工具动作描述", required=True),
                ToolParameter("input_summary", "string", "输入摘要（可选）", required=False),
            ],
            "op_end": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("record_id", "string", "op_start 返回的 ID", required=True),
                ToolParameter("output_summary", "string", "输出摘要（可选）", required=False),
                ToolParameter("status", "string", "success|failed（默认 success）", required=False),
                ToolParameter("error_reason", "string", "失败原因（可选）", required=False),
            ],
            "op_list": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("limit", "integer", "返回条数（可选）", required=False),
            ],
            "diagnostic": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("kind", "string", "token_usage|python_install|tool_json|internal_log", required=True),
                ToolParameter("payload", "string", "诊断内容 JSON（可选）", required=False),
            ],
            "confirm_create": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("operation_type", "string", "操作类型（如 file_write/git_push/command）", required=True),
                ToolParameter("action_label", "string", "操作标签（可选）", required=False),
                ToolParameter("params", "string", "操作参数 JSON（可选）", required=False),
                ToolParameter("reason", "string", "风险说明（可选）", required=False),
            ],
            "confirm_resolve": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("confirmation_id", "string", "确认 ID", required=True),
                ToolParameter("choice", "string", "allow_once|trust_project|reject", required=True),
            ],
            "confirm_pending": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
            ],
            "confirm_is_trusted": [
                ToolParameter("workspace_root", "string", "项目工作区根目录", required=True),
                ToolParameter("operation_type", "string", "操作类型", required=True),
            ],
        },
    )

    def __init__(self, project_manager: Any = None) -> None:
        super().__init__()
        self.project_manager = project_manager

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        try:
            if action == "attach":
                return self._attach(parameters)
            if action == "delete_attachment":
                return self._delete_attachment(parameters)
            if action == "attach_list":
                return self._attach_list(parameters)
            if action == "status_set":
                return self._status_set(parameters)
            if action == "status_get":
                return self._status_get(parameters)
            if action == "op_start":
                return self._op_start(parameters)
            if action == "op_end":
                return self._op_end(parameters)
            if action == "op_list":
                return self._op_list(parameters)
            if action == "diagnostic":
                return self._diagnostic(parameters)
            if action == "confirm_create":
                return self._confirm_create(parameters)
            if action == "confirm_resolve":
                return self._confirm_resolve(parameters)
            if action == "confirm_pending":
                return self._confirm_pending(parameters)
            if action == "confirm_is_trusted":
                return self._confirm_is_trusted(parameters)
        except Exception as exc:  # defensive
            return ToolResult(success=False, data=None, error=f"{type(exc).__name__}: {exc}")
        return ToolResult(success=False, data=None, error=f"Unsupported action '{action}'")

    # -- attachments -------------------------------------------------------
    def _attach(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        path = str(params.get("path") or "")
        if not path:
            return ToolResult(success=False, data=None, error="path is required")
        try:
            manager = att_mod.AttachmentsManager(ws)
            attachment = manager.add(path)
        except att_mod.AttachmentError as exc:
            return ToolResult(
                success=False,
                data={"reason": exc.reason},
                error=exc.args[0] if exc.args else str(exc),
            )
        return ToolResult(success=True, data=attachment.to_dict())

    def _delete_attachment(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        attachment_id = str(params.get("attachment_id") or "")
        manager = att_mod.AttachmentsManager(ws)
        ok = manager.delete(attachment_id)
        return ToolResult(success=ok, data={"deleted": ok})

    def _attach_list(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        manager = att_mod.AttachmentsManager(ws)
        return ToolResult(success=True, data={"attachments": [a.to_dict() for a in manager.list()]})

    # -- status ------------------------------------------------------------
    def _status_set(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        mgr = ss_mod.StatusManager(ws)
        try:
            current = mgr.set(str(params.get("state")), detail=params.get("detail"))
        except ValueError as exc:
            return ToolResult(success=False, data=None, error=str(exc))
        return ToolResult(success=True, data=current)

    def _status_get(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        mgr = ss_mod.StatusManager(ws)
        return ToolResult(success=True, data=mgr.current())

    # -- operation log -----------------------------------------------------
    def _op_start(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        log = ol_mod.OperationLog(ws)
        record_id = log.start(str(params.get("action")), input_summary=str(params.get("input_summary") or ""))
        return ToolResult(success=True, data={"record_id": record_id})

    def _op_end(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        log = ol_mod.OperationLog(ws)
        log.end(
            str(params.get("record_id")),
            output_summary=str(params.get("output_summary") or ""),
            status=str(params.get("status") or "success"),
            error_reason=str(params.get("error_reason") or ""),
        )
        return ToolResult(success=True, data={"ok": True})

    def _op_list(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        log = ol_mod.OperationLog(ws)
        limit = params.get("limit")
        records = log.list(limit=int(limit) if limit is not None else None)
        return ToolResult(success=True, data={"records": records})

    # -- diagnostics -------------------------------------------------------
    def _diagnostic(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        kind = str(params.get("kind") or "")
        payload = _parse_json(params.get("payload"), params.get("payload"))
        try:
            ol_mod.DiagnosticsLog(ws).append(kind, payload)
        except ValueError as exc:
            return ToolResult(success=False, data=None, error=str(exc))
        return ToolResult(success=True, data={"ok": True})

    # -- confirmation ------------------------------------------------------
    def _confirm_create(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        store = conf_mod.ConfirmationStore(ws)
        conf = store.create(
            operation_type=str(params.get("operation_type") or ""),
            action_label=str(params.get("action_label") or params.get("operation_type") or ""),
            params=_parse_json(params.get("params"), {}),
            reason=str(params.get("reason") or ""),
        )
        return ToolResult(success=True, data=conf.to_dict())

    def _confirm_resolve(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        store = conf_mod.ConfirmationStore(ws)
        try:
            conf = store.resolve(str(params.get("confirmation_id")), str(params.get("choice")))
        except ValueError as exc:
            return ToolResult(success=False, data=None, error=str(exc))
        if conf is None:
            return ToolResult(success=False, data=None, error="未找到该确认")
        return ToolResult(success=True, data=conf.to_dict())

    def _confirm_pending(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        store = conf_mod.ConfirmationStore(ws)
        pending = [c.to_dict() for c in store.pending()]
        return ToolResult(success=True, data={"pending": pending})

    def _confirm_is_trusted(self, params: dict[str, Any]) -> ToolResult:
        ws = _ws(params)
        store = conf_mod.ConfirmationStore(ws)
        return ToolResult(success=True, data={"trusted": store.is_trusted(str(params.get("operation_type") or ""))})
