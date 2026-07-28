"""Persistent confirmation queue (feature 3.4, requirements #4 and #5).

A confirmation is created before a risky operation (file write, delete, command,
git push, hardware upload, ...). The user may:

* ``allow_once``    -- permit this single execution
* ``trust_project`` -- permit every future operation of this type in this project
* ``reject``        -- refuse; the operation must NOT execute

Pending confirmations are persisted to ``<workspace>/.kyrozen/`` so they survive
an app restart. On restart the cards are restored and shown again, but the
underlying operation is NEVER auto-executed -- the user must decide again.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The three user-facing choices required by requirement #4.
CHOICES: tuple[str, ...] = ("allow_once", "trust_project", "reject")

# Status values a confirmation can hold.
STATUS_PENDING = "pending"
STATUS_ALLOWED = "allowed"
STATUS_TRUSTED = "trusted"
STATUS_REJECTED = "rejected"


@dataclass
class PendingConfirmation:
    id: str
    operation_type: str
    action_label: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    created_at: float = 0.0
    status: str = STATUS_PENDING
    resolved_at: float | None = None
    auto_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "action_label": self.action_label,
            "params": self.params,
            "reason": self.reason,
            "created_at": self.created_at,
            "status": self.status,
            "resolved_at": self.resolved_at,
            "auto_allowed": self.auto_allowed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PendingConfirmation":
        return cls(
            id=d["id"],
            operation_type=d["operation_type"],
            action_label=d["action_label"],
            params=d.get("params", {}) or {},
            reason=d.get("reason", ""),
            created_at=d.get("created_at", 0.0),
            status=d.get("status", STATUS_PENDING),
            resolved_at=d.get("resolved_at"),
            auto_allowed=d.get("auto_allowed", False),
        )


class ConfirmationStore:
    """Persisted confirmation queue for a single workspace."""

    def __init__(self, workspace: str | Path) -> None:
        self.dir = Path(workspace) / ".kyrozen"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "confirmations.json"
        self.trusted_path = self.dir / "trusted_ops.json"
        self._all = self._load_index()

    # -- persistence -------------------------------------------------------
    def _load_index(self) -> list[PendingConfirmation]:
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            return [PendingConfirmation.from_dict(d) for d in raw.get("confirmations", [])]
        except Exception:
            return []

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(
                {"confirmations": [c.to_dict() for c in self._all]}, ensure_ascii=False
            ),
            encoding="utf-8",
        )

    def _load_trusted(self) -> set[str]:
        try:
            return set(json.loads(self.trusted_path.read_text(encoding="utf-8")).get("trusted", []))
        except Exception:
            return set()

    def _save_trusted(self, trusted: set[str]) -> None:
        self.trusted_path.write_text(
            json.dumps({"trusted": sorted(trusted)}, ensure_ascii=False), encoding="utf-8"
        )

    # -- API ---------------------------------------------------------------
    def is_trusted(self, operation_type: str) -> bool:
        return operation_type in self._load_trusted()

    def create(
        self,
        operation_type: str,
        action_label: str,
        params: dict[str, Any] | None = None,
        reason: str = "",
    ) -> PendingConfirmation:
        """Create a confirmation. If the type is already trusted for this project,
        the record is created pre-allowed (no prompt needed)."""
        if self.is_trusted(operation_type):
            conf = PendingConfirmation(
                id=f"conf_{uuid.uuid4().hex[:10]}",
                operation_type=operation_type,
                action_label=action_label,
                params=params or {},
                reason=reason,
                created_at=time.time(),
                status=STATUS_ALLOWED,
                auto_allowed=True,
            )
        else:
            conf = PendingConfirmation(
                id=f"conf_{uuid.uuid4().hex[:10]}",
                operation_type=operation_type,
                action_label=action_label,
                params=params or {},
                reason=reason,
                created_at=time.time(),
            )
        self._all.append(conf)
        self._save_index()
        return conf

    def resolve(self, confirmation_id: str, choice: str) -> PendingConfirmation | None:
        if choice not in CHOICES:
            raise ValueError(f"choice 必须是 {CHOICES} 之一")
        conf = next((c for c in self._all if c.id == confirmation_id), None)
        if conf is None:
            return None
        if choice == "allow_once":
            conf.status = STATUS_ALLOWED
        elif choice == "trust_project":
            conf.status = STATUS_TRUSTED
            trusted = self._load_trusted()
            trusted.add(conf.operation_type)
            self._save_trusted(trusted)
        elif choice == "reject":
            conf.status = STATUS_REJECTED
        conf.resolved_at = time.time()
        self._save_index()
        return conf

    def pending(self) -> list[PendingConfirmation]:
        return [c for c in self._all if c.status == STATUS_PENDING]

    def status_of(self, confirmation_id: str) -> str | None:
        conf = next((c for c in self._all if c.id == confirmation_id), None)
        return conf.status if conf is not None else None

    def should_execute(self, operation_type: str) -> tuple[bool, str | None]:
        """Return ``(execute?, pending_id_or_None)``.

        ``execute`` is True when the operation type is trusted (or there is no
        pending requirement). Otherwise a pending confirmation is created and its
        id is returned so the caller can block until the user decides.
        """
        if self.is_trusted(operation_type):
            return True, None
        conf = self.create(operation_type, operation_type, reason="需要用户确认")
        return False, conf.id

    def restore(self) -> list[PendingConfirmation]:
        """Load pending confirmations from disk (used after an app restart)."""
        self._all = self._load_index()
        return self.pending()
