"""Structured logging system for Kyrozen Core.

Records: user requests, agent decisions, model calls, tool calls, errors, performance.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LogEntry:
    """A single structured log entry."""

    event_type: str  # user, agent, model, tool, error, perf
    message: str
    task_id: str = ""
    metadata: dict[str, Any] | None = None
    timestamp: str = ""
    entry_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.entry_id:
            self.entry_id = f"log_{uuid.uuid4().hex[:8]}"
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KyrozenLogger:
    """Thread-safe structured logger with file + stdout output."""

    def __init__(self, log_level: str = "INFO", log_dir: str = "./logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"kyrozen_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"

        self.logger = logging.getLogger("kyrozen")
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.logger.handlers = []

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        self.logger.addHandler(console)

        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        self.logger.addHandler(file_handler)

        self.entries: list[LogEntry] = []

    def _write_structured(self, entry: LogEntry) -> None:
        try:
            with open(self.log_dir / "kyrozen_events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def log(self, event_type: str, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        entry = LogEntry(event_type=event_type, message=message, task_id=task_id, metadata=metadata)
        self.entries.append(entry)
        self._write_structured(entry)
        self.logger.info("[%s] %s | task=%s | %s", event_type, message, task_id, json.dumps(metadata, ensure_ascii=False))
        return entry

    def user(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("user", message, task_id, **metadata)

    def agent(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("agent", message, task_id, **metadata)

    def model(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("model", message, task_id, **metadata)

    def tool(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("tool", message, task_id, **metadata)

    def error(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("error", message, task_id, **metadata)

    def warning(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("warning", message, task_id, **metadata)

    def perf(self, message: str, task_id: str = "", **metadata: Any) -> LogEntry:
        return self.log("perf", message, task_id, **metadata)


_LOGGER: KyrozenLogger | None = None


def get_logger(log_level: str | None = None, log_dir: str = "./logs") -> KyrozenLogger:
    """Return the singleton logger, creating it if needed."""
    global _LOGGER
    if _LOGGER is None:
        level = log_level or os.environ.get("KYROZEN_LOG_LEVEL", "INFO")
        _LOGGER = KyrozenLogger(log_level=level, log_dir=log_dir)
    return _LOGGER
