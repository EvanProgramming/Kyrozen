"""Non-coding deliverable templates (Phase 1, 3.3 — requirement #8).

For non-software projects Kyrozen must still produce a typed, structured
deliverable. This module defines four templates — research report, content
plan, operations plan, and business-process design — each with a fixed field
schema and a Markdown renderer, and persists them under
``<workspace>/.kyrozen/deliverables.json`` for traceability.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NONCODING_TYPES = {
    "research_report",
    "content_plan",
    "ops_plan",
    "business_process",
}

# Field schema per deliverable type. ``kind`` is "text" or "list".
NONCODING_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "research_report": [
        {"name": "background", "label": "研究背景", "kind": "text", "required": True},
        {"name": "question", "label": "研究问题", "kind": "text", "required": True},
        {"name": "method", "label": "研究方法", "kind": "text", "required": False},
        {"name": "findings", "label": "关键发现", "kind": "list", "required": True},
        {"name": "sources", "label": "来源清单", "kind": "list", "required": False},
        {"name": "conclusion", "label": "结论与建议", "kind": "text", "required": True},
    ],
    "content_plan": [
        {"name": "audience", "label": "目标受众", "kind": "text", "required": True},
        {"name": "message", "label": "核心信息", "kind": "text", "required": True},
        {"name": "channels", "label": "发布渠道", "kind": "list", "required": False},
        {"name": "topics", "label": "内容主题", "kind": "list", "required": True},
        {"name": "cadence", "label": "发布节奏", "kind": "text", "required": False},
        {"name": "metrics", "label": "度量指标", "kind": "list", "required": False},
    ],
    "ops_plan": [
        {"name": "goal", "label": "目标", "kind": "text", "required": True},
        {"name": "scope", "label": "范围", "kind": "text", "required": False},
        {"name": "processes", "label": "关键流程", "kind": "list", "required": True},
        {"name": "owners", "label": "责任分工", "kind": "text", "required": False},
        {"name": "timeline", "label": "时间表", "kind": "text", "required": False},
        {"name": "risks", "label": "风险与应对", "kind": "list", "required": False},
    ],
    "business_process": [
        {"name": "name", "label": "流程名称", "kind": "text", "required": True},
        {"name": "trigger", "label": "触发条件", "kind": "text", "required": True},
        {"name": "steps", "label": "步骤", "kind": "list", "required": True},
        {"name": "roles", "label": "角色", "kind": "list", "required": False},
        {"name": "io", "label": "输入与输出", "kind": "text", "required": False},
        {"name": "exceptions", "label": "异常处理", "kind": "list", "required": False},
    ],
}

_TEMPLATE_HEAD = {
    "research_report": "研究报告",
    "content_plan": "内容方案",
    "ops_plan": "运营计划",
    "business_process": "业务流程设计",
}

_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "research_report": {
        "背景": "background", "研究背景": "background",
        "问题": "question", "研究问题": "question", "目标": "question",
        "方法": "method", "研究方法": "method",
        "发现": "findings", "关键发现": "findings", "重点": "findings", "对比对象": "findings",
        "来源": "sources", "来源清单": "sources",
        "结论": "conclusion", "建议": "conclusion", "结论与建议": "conclusion",
    },
    "content_plan": {"受众": "audience", "目标受众": "audience", "核心信息": "message", "渠道": "channels", "发布渠道": "channels", "主题": "topics", "内容主题": "topics", "节奏": "cadence", "发布节奏": "cadence", "指标": "metrics", "度量指标": "metrics"},
    "ops_plan": {"目标": "goal", "范围": "scope", "流程": "processes", "关键流程": "processes", "负责人": "owners", "责任分工": "owners", "时间": "timeline", "时间表": "timeline", "风险": "risks", "风险与应对": "risks"},
    "business_process": {"名称": "name", "流程名称": "name", "触发": "trigger", "触发条件": "trigger", "步骤": "steps", "角色": "roles", "输入输出": "io", "输入与输出": "io", "异常": "exceptions", "异常处理": "exceptions"},
}


def normalize_fields(deliverable_type: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Accept both schema keys and ordinary Chinese labels from the desktop form."""
    schema_names = {item["name"] for item in NONCODING_SCHEMAS[deliverable_type]}
    aliases = _FIELD_ALIASES.get(deliverable_type, {})
    normalized: dict[str, Any] = {}
    for raw_key, value in fields.items():
        key = str(raw_key).strip()
        canonical = key if key in schema_names else aliases.get(key)
        if not canonical:
            continue
        if canonical in normalized and normalized[canonical] and value:
            normalized[canonical] = f"{normalized[canonical]}\n{value}"
        else:
            normalized[canonical] = value
    return normalized


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower())
    return s.strip("_") or "deliverable"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _bullets(items: list[str]) -> str:
    if not items:
        return "_（未填写）_"
    return "\n".join(f"- {it}" for it in items)


def render_markdown(deliverable_type: str, title: str, fields: dict[str, Any]) -> str:
    """Render a non-coding deliverable to Markdown using its template."""
    if deliverable_type not in NONCODING_TYPES:
        raise ValueError(f"Unknown deliverable type '{deliverable_type}'")
    head = _TEMPLATE_HEAD[deliverable_type]
    lines = [f"# {title}", "", f"> 类型：{head}", ""]

    def section(label: str, body: str) -> None:
        lines.append(f"## {label}")
        lines.append(body)
        lines.append("")

    if deliverable_type == "research_report":
        section("研究背景", str(fields.get("background") or "_（未填写）_"))
        section("研究问题", str(fields.get("question") or "_（未填写）_"))
        section("研究方法", str(fields.get("method") or "_（未填写）_"))
        section("关键发现", _bullets(_as_list(fields.get("findings"))))
        section("来源清单", _bullets(_as_list(fields.get("sources"))))
        section("结论与建议", str(fields.get("conclusion") or "_（未填写）_"))
    elif deliverable_type == "content_plan":
        section("目标受众", str(fields.get("audience") or "_（未填写）_"))
        section("核心信息", str(fields.get("message") or "_（未填写）_"))
        section("发布渠道", _bullets(_as_list(fields.get("channels"))))
        section("内容主题", _bullets(_as_list(fields.get("topics"))))
        section("发布节奏", str(fields.get("cadence") or "_（未填写）_"))
        section("度量指标", _bullets(_as_list(fields.get("metrics"))))
    elif deliverable_type == "ops_plan":
        section("目标", str(fields.get("goal") or "_（未填写）_"))
        section("范围", str(fields.get("scope") or "_（未填写）_"))
        section("关键流程", _bullets(_as_list(fields.get("processes"))))
        section("责任分工", str(fields.get("owners") or "_（未填写）_"))
        section("时间表", str(fields.get("timeline") or "_（未填写）_"))
        section("风险与应对", _bullets(_as_list(fields.get("risks"))))
    elif deliverable_type == "business_process":
        section("流程名称", str(fields.get("name") or "_（未填写）_"))
        section("触发条件", str(fields.get("trigger") or "_（未填写）_"))
        section("步骤", _bullets(_as_list(fields.get("steps"))))
        section("角色", _bullets(_as_list(fields.get("roles"))))
        section("输入与输出", str(fields.get("io") or "_（未填写）_"))
        section("异常处理", _bullets(_as_list(fields.get("exceptions"))))
    return "\n".join(lines).rstrip() + "\n"


@dataclass
class DeliverableResult:
    deliverable_type: str = ""
    title: str = ""
    file: str = ""
    markdown: str = ""
    record: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_type": self.deliverable_type,
            "title": self.title,
            "file": self.file,
            "markdown": self.markdown,
            "record": self.record,
        }


def build_deliverable(
    deliverable_type: str,
    title: str,
    fields: dict[str, Any],
    workspace: str | Path,
) -> DeliverableResult:
    """Render and persist a non-coding deliverable to the workspace."""
    if deliverable_type not in NONCODING_TYPES:
        raise ValueError(f"Unknown deliverable type '{deliverable_type}'")
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    fields = normalize_fields(deliverable_type, fields)
    md = render_markdown(deliverable_type, title, fields)
    fname = f"{slugify(title)}_{deliverable_type}.md"
    fpath = ws / fname
    fpath.write_text(md, encoding="utf-8")

    record = {
        "deliverable_type": deliverable_type,
        "title": title,
        "fields": fields,
        "file": fname,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Append to the local deliverables log (mirrors handoff/stagegate).
    state_dir = ws / ".kyrozen"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "deliverables.json"
    existing: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8")) or []
        except Exception:
            existing = []
    existing.append(record)
    log_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    return DeliverableResult(
        deliverable_type=deliverable_type,
        title=title,
        file=str(fpath),
        markdown=md,
        record=record,
    )
