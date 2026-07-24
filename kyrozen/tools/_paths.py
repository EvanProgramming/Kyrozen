"""Path safety helpers for Kyrozen tools.

All file-system and shell tools must restrict operations to a well-defined
workspace so that an agent cannot read or write arbitrary host files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _get_allowed_root(parameters: dict[str, Any]) -> Path:
    """Return the allowed workspace for the current tool call.

    If ``project_id`` is provided, the project directory is used. Otherwise the
    global ``workspace_root`` from the active configuration is used.
    """
    from kyrozen.config import get_config

    config = get_config()
    project_id = parameters.get("project_id")
    if project_id:
        return Path(config.project_dir(str(project_id))).resolve()
    return Path(config.workspace_root).resolve()


def _resolve_safe_path(
    raw_path: str, allowed_root: Path, project_id: str | None = None
) -> tuple[Path | None, str]:
    """Resolve ``raw_path`` against ``allowed_root`` and enforce containment.

    Relative paths are resolved relative to ``allowed_root``. Absolute paths are
    only allowed when they point inside ``allowed_root``. Returns ``(path, "")``
    on success or ``(None, error_message)`` on failure.

    Agents often express paths relative to the workspace root (e.g.
    ``projects/{project_id}/software/...``). When ``project_id`` is provided,
    such prefixes are stripped so the path resolves inside the project directory
    instead of being doubled.
    """
    if not raw_path:
        return None, "Path is required"

    normalized = raw_path.replace("\\", "/").strip("/")
    if project_id:
        prefixes = (
            f"projects/{project_id}/",
            f"projects/{project_id}",
            f"{project_id}/",
            f"{project_id}",
        )
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].lstrip("/")
                break

    expanded = Path(os.path.expanduser(normalized))
    if expanded.is_absolute():
        target = expanded.resolve()
    else:
        target = (allowed_root / expanded).resolve()

    try:
        target.relative_to(allowed_root)
    except ValueError:
        return None, f"Path '{raw_path}' is outside the allowed workspace '{allowed_root}'"

    return target, ""
