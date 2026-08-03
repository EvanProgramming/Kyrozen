"""Persistent membership policy and dual Credit/cost accounting.

The service deliberately keeps billing-provider integration out of the policy
layer.  A payment webhook can call ``set_plan`` later without changing quota
enforcement or usage history.
"""

from __future__ import annotations

import json
import math
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active',
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    price_rmb REAL NOT NULL DEFAULT 0,
    monthly_cost_limit_rmb REAL NOT NULL DEFAULT 0,
    free_subsidy_limit_rmb REAL NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS membership_seats (
    owner_user_id TEXT NOT NULL,
    member_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_user_id, member_user_id)
);
CREATE TABLE IF NOT EXISTS project_creation_events (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_creation_owner ON project_creation_events(owner_user_id, created_at);
CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    task_id TEXT,
    kind TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    credits INTEGER NOT NULL DEFAULT 0,
    cost_rmb REAL NOT NULL DEFAULT 0,
    formula_version TEXT NOT NULL DEFAULT 'v1',
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_owner_time ON usage_events(owner_user_id, created_at);
CREATE TABLE IF NOT EXISTS task_budget_states (
    task_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'running',
    reason TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS afdian_accounts (
    user_id TEXT PRIMARY KEY,
    afdian_user_id TEXT UNIQUE NOT NULL,
    afdian_user_private_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS afdian_oauth_states (
    state TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS afdian_checkout_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    plan TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    checkout_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS afdian_orders (
    out_trade_no TEXT PRIMARY KEY,
    user_id TEXT,
    afdian_user_id TEXT,
    afdian_user_private_id TEXT,
    plan TEXT,
    plan_id TEXT,
    month INTEGER NOT NULL DEFAULT 1,
    total_amount REAL,
    status INTEGER,
    raw_payload TEXT,
    verification_status TEXT NOT NULL DEFAULT 'pending',
    review_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS membership_grants (
    id TEXT PRIMARY KEY,
    out_trade_no TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    plan TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS membership_payment_reviews (
    id TEXT PRIMARY KEY,
    out_trade_no TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    metadata TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT
);
"""


@dataclass(frozen=True)
class PlanPolicy:
    plan: str
    price_rmb: float
    active_projects: int
    monthly_creations: int
    weekly_credits: int
    conversations: int
    five_hour_credits: int
    monthly_cost_limit_rmb: float
    max_seats: int
    graceful_overage: bool
    max_concurrent_tasks: int


POLICIES: dict[str, PlanPolicy] = {
    "free": PlanPolicy("free", 0, 1, 1, 1000, 20, 250, 1.0, 0, False, 1),
    "lite": PlanPolicy("lite", 24, 5, 5, 3000, 0, 750, 19.2, 0, False, 1),
    "pro": PlanPolicy("pro", 140, 20, 20, 10000, 0, 0, 112.0, 0, True, 2),
    "ultimate": PlanPolicy("ultimate", 2999, 0, 0, 0, 0, 0, 2699.1, 3, True, 4),
    # Not exposed by the API yet; retained for future institution onboarding.
    "enterprise": PlanPolicy("enterprise", 0, 0, 0, 0, 0, 0, 0, 20, True, 20),
}


@dataclass(frozen=True)
class UsageEstimate:
    credits: int
    cost_rmb: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    tool_calls: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


class MembershipService:
    """Membership policy backed by the configured project database."""

    formula_version = "v1"

    def __init__(self, db: Any, config: Any | None = None, *, free_subsidy_limit_rmb: float = 1.0) -> None:
        self.db = db
        self.provider_costs = dict(getattr(config, "provider_costs", {}) or {})
        self.usd_to_rmb = float(getattr(config, "membership_usd_to_rmb", 7.3) or 7.3)
        self.free_subsidy_limit_rmb = max(0.0, float(free_subsidy_limit_rmb))
        self._lock = threading.RLock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if hasattr(self.db, "db_path"):
            with self.db._lock, self.db._connect() as conn:
                conn.executescript(SCHEMA_SQL)
            return
        # PostgresDatabase exposes a safe parameterized execution helper.  The
        # Supabase deployment uses migrations/002_memberships.sql instead.
        if hasattr(self.db, "_execute"):
            for statement in SCHEMA_SQL.split(";"):
                statement = statement.strip()
                if statement:
                    self.db._execute(statement)

    @property
    def _is_supabase(self) -> bool:
        return hasattr(self.db, "client") and not hasattr(self.db, "db_path")

    def _supabase_query(self, table: str, filters: list[tuple[str, Any]], *, order: str | None = None) -> list[dict[str, Any]]:
        query = self.db.client.table(table).select("*")
        for column, value in filters:
            query = query.eq(column, value)
        if order:
            query = query.order(order)
        response = query.execute()
        return list(getattr(response, "data", []) or [])

    def _query(self, sql: str, params: tuple[Any, ...] = (), *, all_rows: bool = False) -> Any:
        if hasattr(self.db, "db_path"):
            with self.db._lock, self.db._connect() as conn:
                cursor = conn.execute(sql, params)
                rows = cursor.fetchall() if all_rows else cursor.fetchone()
                return [dict(row) for row in rows] if all_rows else (dict(rows) if rows else None)
        if hasattr(self.db, "_execute"):
            return self.db._execute(sql, params, fetch="all" if all_rows else "one")
        if not self._is_supabase:
            raise RuntimeError("Unsupported database adapter for membership store")
        if "FROM memberships" in sql:
            rows = self._supabase_query("memberships", [("user_id", params[0])])
            return rows if all_rows else (rows[0] if rows else None)
        if "FROM membership_seats" in sql:
            filters = [("owner_user_id", params[0])] if "owner_user_id = ?" in sql else [("member_user_id", params[0]), ("status", "active")]
            if "member_user_id = ?" in sql and len(params) > 1:
                filters = [("owner_user_id", params[0]), ("member_user_id", params[1])]
            rows = self._supabase_query("membership_seats", filters, order="created_at")
            if "SELECT 1 AS found" in sql:
                return {"found": 1} if rows else None
            return rows if all_rows else (rows[0] if rows else None)
        if "FROM project_creation_events" in sql:
            rows = self._supabase_query("project_creation_events", [("owner_user_id", params[0])])
            start = str(params[1])
            end = str(params[2]) if len(params) > 2 else None
            count = sum(1 for row in rows if str(row.get("created_at", "")) >= start and (end is None or str(row.get("created_at", "")) < end))
            return {"count": count}
        if "FROM usage_events" in sql:
            rows = self._supabase_query("usage_events", [("owner_user_id", params[0])])
            start = str(params[1])
            end = str(params[2]) if len(params) > 2 else None
            kind = params[3] if "AND kind = ?" in sql else None
            selected = [row for row in rows if str(row.get("created_at", "")) >= start and (end is None or str(row.get("created_at", "")) < end) and (kind is None or row.get("kind") == kind)]
            return {"credits": sum(float(row.get("credits") or 0) for row in selected), "cost": sum(float(row.get("cost_rmb") or 0) for row in selected), "conversations": len(selected)}
        if "FROM afdian_accounts" in sql:
            filters = [("user_id", params[0])] if "user_id = ?" in sql else [("afdian_user_id", params[0])]
            rows = self._supabase_query("afdian_accounts", filters)
            return rows if all_rows else (rows[0] if rows else None)
        if "FROM afdian_checkout_sessions" in sql:
            filters = [("id", params[0])]
            if len(params) > 1:
                filters.append(("user_id", params[1]))
            rows = self._supabase_query("afdian_checkout_sessions", filters)
            return rows if all_rows else (rows[0] if rows else None)
        if "FROM afdian_oauth_states" in sql:
            rows = self._supabase_query("afdian_oauth_states", [("state", params[0])])
            return rows if all_rows else (rows[0] if rows else None)
        for table in ("afdian_orders", "membership_grants", "membership_payment_reviews"):
            if f"FROM {table}" in sql:
                rows = self._supabase_query(table, [])
                if "out_trade_no = ?" in sql:
                    rows = [r for r in rows if str(r.get("out_trade_no")) == str(params[0])]
                if "id = ?" in sql:
                    rows = [r for r in rows if str(r.get("id")) == str(params[0])]
                return rows if all_rows else (rows[0] if rows else None)
        raise RuntimeError("Unsupported Supabase membership query")

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if hasattr(self.db, "db_path"):
            with self.db._lock, self.db._connect() as conn:
                conn.execute(sql, params)
                conn.commit()
            return
        if hasattr(self.db, "_execute"):
            self.db._execute(sql, params)
            return
        raise RuntimeError("Supabase membership writes must use the typed store methods")

    def _owner(self, user_id: str) -> str:
        row = self._query(
            "SELECT owner_user_id FROM membership_seats WHERE member_user_id = ? AND status = 'active'",
            (user_id,),
        )
        return str(row["owner_user_id"]) if row else user_id

    def _ensure_account(self, user_id: str) -> dict[str, Any]:
        row = self._query("SELECT * FROM memberships WHERE user_id = ?", (user_id,))
        if row:
            return row
        start, end = _month_bounds(_now())
        timestamp = _iso(_now())
        if self._is_supabase:
            self.db.client.table("memberships").insert({"user_id": user_id, "plan": "free", "status": "active", "period_start": _iso(start), "period_end": _iso(end), "price_rmb": 0, "monthly_cost_limit_rmb": 0, "free_subsidy_limit_rmb": self.free_subsidy_limit_rmb, "created_at": timestamp, "updated_at": timestamp}).execute()
            return self._query("SELECT * FROM memberships WHERE user_id = ?", (user_id,))
        self._execute(
            """INSERT INTO memberships
               (user_id, plan, status, period_start, period_end, price_rmb,
                monthly_cost_limit_rmb, free_subsidy_limit_rmb, created_at, updated_at)
               VALUES (?, 'free', 'active', ?, ?, 0, 0, ?, ?, ?)""",
            (user_id, _iso(start), _iso(end), self.free_subsidy_limit_rmb, timestamp, timestamp),
        )
        return self._query("SELECT * FROM memberships WHERE user_id = ?", (user_id,))

    def membership(self, user_id: str) -> dict[str, Any]:
        owner = self._owner(user_id)
        row = self._ensure_account(owner)
        start, end = _month_bounds(_now())
        if _parse(row["period_end"]) <= _now():
            if self._is_supabase:
                self.db.client.table("memberships").update({"period_start": _iso(start), "period_end": _iso(end), "updated_at": _iso(_now())}).eq("user_id", owner).execute()
            else:
                self._execute(
                "UPDATE memberships SET period_start = ?, period_end = ?, updated_at = ? WHERE user_id = ?",
                (_iso(start), _iso(end), _iso(_now()), owner),
                )
            row = self._query("SELECT * FROM memberships WHERE user_id = ?", (owner,))
        row["owner_user_id"] = owner
        row["member_user_id"] = user_id
        return row

    def policy(self, user_id: str, *, plan_override: str | None = None) -> PlanPolicy:
        plan = plan_override or str(self.membership(user_id)["plan"])
        return POLICIES.get(plan, POLICIES["free"])

    def set_plan(self, user_id: str, plan: str, *, status: str = "active") -> dict[str, Any]:
        if plan not in POLICIES:
            raise ValueError(f"Unknown membership plan: {plan}")
        policy = POLICIES[plan]
        start, end = _month_bounds(_now())
        self._ensure_account(user_id)
        if self._is_supabase:
            self.db.client.table("memberships").update({"plan": plan, "status": status, "period_start": _iso(start), "period_end": _iso(end), "price_rmb": policy.price_rmb, "monthly_cost_limit_rmb": policy.monthly_cost_limit_rmb, "updated_at": _iso(_now())}).eq("user_id", user_id).execute()
        else:
            self._execute(
            """UPDATE memberships SET plan = ?, status = ?, period_start = ?, period_end = ?,
               price_rmb = ?, monthly_cost_limit_rmb = ?, updated_at = ? WHERE user_id = ?""",
            (plan, status, _iso(start), _iso(end), policy.price_rmb, policy.monthly_cost_limit_rmb, _iso(_now()), user_id),
            )
        return self.membership(user_id)

    def project_decision(self, user_id: str, active_project_count: int, *, plan_override: str | None = None) -> tuple[bool, str]:
        row = self.membership(user_id)
        policy = self.policy(user_id, plan_override=plan_override)
        if policy.active_projects and active_project_count >= policy.active_projects:
            if policy.plan == "free":
                return False, "免费账户最多创建一个项目；已有项目可完整使用全部阶段。"
            return False, f"{policy.plan} 会员最多同时拥有 {policy.active_projects} 个项目"
        start = row["period_start"]
        created = self._query(
            "SELECT COUNT(*) AS count FROM project_creation_events WHERE owner_user_id = ? AND created_at >= ? AND created_at < ?",
            (row["owner_user_id"], start, row["period_end"]),
        )
        if policy.monthly_creations and int(created["count"]) >= policy.monthly_creations:
            return False, f"{policy.plan} 会员本订阅月最多创建 {policy.monthly_creations} 个项目"
        return True, "ok"

    def record_project_creation(self, user_id: str, project_id: str) -> None:
        owner = self._owner(user_id)
        if self._is_supabase:
            self.db.client.table("project_creation_events").insert({"id": str(uuid.uuid4()), "owner_user_id": owner, "project_id": project_id, "created_at": _iso(_now())}).execute()
            return
        self._execute(
            "INSERT INTO project_creation_events (id, owner_user_id, project_id, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), owner, project_id, _iso(_now())),
        )

    def estimate(self, *, prompt_tokens: int, completion_tokens: int = 0, cache_hit_tokens: int = 0, tool_calls: int = 0, provider: str = "", model: str = "") -> UsageEstimate:
        prompt_tokens = max(0, int(prompt_tokens))
        completion_tokens = max(0, int(completion_tokens))
        cache_hit_tokens = max(0, min(int(cache_hit_tokens), prompt_tokens))
        tool_calls = max(0, int(tool_calls))
        model_factor = 1.0
        context_factor = 1.0 + min(prompt_tokens / 100_000, 1.0) * 0.25
        tool_factor = 1.0 + min(tool_calls * 0.05, 0.5)
        credits = math.ceil(((prompt_tokens + 2 * completion_tokens + 0.1 * cache_hit_tokens) / 1000) * model_factor * context_factor * tool_factor)
        provider_key = (provider or "deepseek").split("/", 1)[0].lower()
        input_rate, output_rate = self.provider_costs.get(provider_key, (0.435, 0.87))
        cache_hit_rate = 0.003625 if provider_key == "deepseek" else input_rate
        cost_rmb = ((prompt_tokens - cache_hit_tokens) * input_rate + cache_hit_tokens * cache_hit_rate + completion_tokens * output_rate) / 1_000_000 * self.usd_to_rmb
        return UsageEstimate(credits=max(0, credits), cost_rmb=max(0.0, cost_rmb), prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cache_hit_tokens=cache_hit_tokens, tool_calls=tool_calls)

    def _sum(self, owner: str, start: datetime, end: datetime | None = None, *, kind: str | None = None) -> dict[str, float]:
        if end is None:
            sql = "SELECT COALESCE(SUM(credits), 0) AS credits, COALESCE(SUM(cost_rmb), 0) AS cost, COUNT(*) AS conversations FROM usage_events WHERE owner_user_id = ? AND created_at >= ?"
            params: tuple[Any, ...] = (owner, _iso(start))
        else:
            sql = "SELECT COALESCE(SUM(credits), 0) AS credits, COALESCE(SUM(cost_rmb), 0) AS cost, COUNT(*) AS conversations FROM usage_events WHERE owner_user_id = ? AND created_at >= ? AND created_at < ?"
            params = (owner, _iso(start), _iso(end))
        if kind:
            sql += " AND kind = ?"
            params += (kind,)
        row = self._query(sql, params)
        return {"credits": float(row["credits"] or 0), "cost": float(row["cost"] or 0), "conversations": float(row["conversations"] or 0)}

    def check(self, user_id: str, estimate: UsageEstimate | None = None, *, conversation: bool = False, plan_override: str | None = None) -> dict[str, Any]:
        row = self.membership(user_id)
        policy = self.policy(user_id, plan_override=plan_override)
        owner = row["owner_user_id"]
        now = _now()
        weekly_start = _parse(row["period_start"])
        weekly_start += timedelta(days=7 * max(0, int((now - weekly_start).total_seconds() // (7 * 86400))))
        weekly = self._sum(owner, weekly_start, min(weekly_start + timedelta(days=7), _parse(row["period_end"])))
        rolling = self._sum(owner, now - timedelta(hours=5))
        monthly = self._sum(owner, _parse(row["period_start"]), _parse(row["period_end"]))
        monthly_conversations = self._sum(owner, _parse(row["period_start"]), _parse(row["period_end"]), kind="conversation")
        add_credits = estimate.credits if estimate else 0
        add_cost = estimate.cost_rmb if estimate else 0.0
        blocked: str | None = None
        if conversation and policy.conversations and monthly_conversations["conversations"] >= policy.conversations:
            blocked = f"本订阅月对话次数已达到 {policy.conversations} 次"
        if not blocked and policy.weekly_credits and weekly["credits"] + add_credits > policy.weekly_credits:
            blocked = "本订阅周 Credit 已用尽"
        if not blocked and policy.five_hour_credits and rolling["credits"] + add_credits > policy.five_hour_credits:
            blocked = "5小时内 Credit 使用过快，请稍后再试"
        if not blocked and policy.monthly_cost_limit_rmb and monthly["cost"] + add_cost > policy.monthly_cost_limit_rmb:
            blocked = "本订阅月成本额度已用尽"
        weekly_end = min(weekly_start + timedelta(days=7), _parse(row["period_end"]))
        return {"allowed": blocked is None, "reason": blocked or "ok", "plan": policy.plan, "used_credits": int(weekly["credits"]), "weekly_limit": policy.weekly_credits, "weekly_reset_at": _iso(weekly_end), "rolling_credits": int(rolling["credits"]), "rolling_limit": policy.five_hour_credits, "rolling_reset_at": _iso(now + timedelta(hours=5)), "monthly_cost_rmb": round(monthly["cost"], 6), "monthly_cost_limit_rmb": policy.monthly_cost_limit_rmb, "conversations": int(monthly_conversations["conversations"]), "conversation_limit": policy.conversations, "period_start": row["period_start"], "period_end": row["period_end"], "graceful": policy.graceful_overage}

    def record_usage(self, user_id: str, estimate: UsageEstimate, *, project_id: str | None = None, task_id: str | None = None, kind: str = "model", provider: str = "", model: str = "", metadata: dict[str, Any] | None = None) -> None:
        owner = self._owner(user_id)
        if self._is_supabase:
            self.db.client.table("usage_events").insert({"id": str(uuid.uuid4()), "owner_user_id": owner, "user_id": user_id, "project_id": project_id, "task_id": task_id, "kind": kind, "provider": provider, "model": model, "prompt_tokens": estimate.prompt_tokens, "completion_tokens": estimate.completion_tokens, "cache_hit_tokens": estimate.cache_hit_tokens, "tool_calls": estimate.tool_calls, "credits": estimate.credits, "cost_rmb": estimate.cost_rmb, "formula_version": self.formula_version, "metadata": metadata or {}, "created_at": _iso(_now())}).execute()
            return
        self._execute(
            """INSERT INTO usage_events
               (id, owner_user_id, user_id, project_id, task_id, kind, provider, model,
                prompt_tokens, completion_tokens, cache_hit_tokens, tool_calls, credits,
                cost_rmb, formula_version, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), owner, user_id, project_id, task_id, kind, provider, model, estimate.prompt_tokens, estimate.completion_tokens, estimate.cache_hit_tokens, estimate.tool_calls, estimate.credits, estimate.cost_rmb, self.formula_version, json.dumps(metadata or {}, ensure_ascii=False), _iso(_now())),
        )

    def status(self, user_id: str, *, plan_override: str | None = None) -> dict[str, Any]:
        return self.check(user_id, plan_override=plan_override)

    def seats(self, user_id: str) -> list[dict[str, Any]]:
        owner = self._owner(user_id)
        return self._query("SELECT * FROM membership_seats WHERE owner_user_id = ? ORDER BY created_at", (owner,), all_rows=True) or []

    def add_seat(self, user_id: str, member_user_id: str) -> dict[str, Any]:
        owner = self._owner(user_id)
        policy = self.policy(owner)
        if policy.max_seats == 0:
            raise ValueError("当前会员档位不支持家庭成员")
        if len(self.seats(owner)) >= policy.max_seats:
            raise ValueError(f"最多添加 {policy.max_seats} 个成员")
        if self._is_supabase:
            self.db.client.table("membership_seats").insert({"owner_user_id": owner, "member_user_id": member_user_id, "status": "active", "created_at": _iso(_now())}).execute()
        else:
            self._execute("INSERT INTO membership_seats (owner_user_id, member_user_id, status, created_at) VALUES (?, ?, 'active', ?)", (owner, member_user_id, _iso(_now())))
        return {"owner_user_id": owner, "member_user_id": member_user_id, "status": "active"}

    def remove_seat(self, user_id: str, member_user_id: str) -> bool:
        owner = self._owner(user_id)
        if owner != user_id:
            return False
        row = self._query("SELECT 1 AS found FROM membership_seats WHERE owner_user_id = ? AND member_user_id = ?", (owner, member_user_id))
        if not row:
            return False
        if self._is_supabase:
            self.db.client.table("membership_seats").delete().eq("owner_user_id", owner).eq("member_user_id", member_user_id).execute()
        else:
            self._execute("DELETE FROM membership_seats WHERE owner_user_id = ? AND member_user_id = ?", (owner, member_user_id))
        return True

    # Payment persistence is kept here so a grant updates the same membership
    # row used by quota checks. SQLite/Postgres use the common SQL adapter;
    # Supabase uses the typed client path.
    def afdian_account(self, user_id: str) -> dict[str, Any] | None:
        return self._query("SELECT * FROM afdian_accounts WHERE user_id = ?", (self._owner(user_id),))

    def bind_afdian_account(self, user_id: str, afdian_user_id: str, user_private_id: str) -> dict[str, Any]:
        owner = self._owner(user_id)
        now = _iso(_now())
        values = {"user_id": owner, "afdian_user_id": str(afdian_user_id), "afdian_user_private_id": str(user_private_id), "status": "active", "updated_at": now}
        if self._is_supabase:
            existing = self.db.client.table("afdian_accounts").select("*").eq("user_id", owner).execute()
            if getattr(existing, "data", None):
                self.db.client.table("afdian_accounts").update(values).eq("user_id", owner).execute()
            else:
                self.db.client.table("afdian_accounts").insert({**values, "created_at": now}).execute()
        else:
            self._execute("INSERT INTO afdian_accounts (user_id, afdian_user_id, afdian_user_private_id, status, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?) ON CONFLICT(user_id) DO UPDATE SET afdian_user_id=excluded.afdian_user_id, afdian_user_private_id=excluded.afdian_user_private_id, status='active', updated_at=excluded.updated_at", (owner, str(afdian_user_id), str(user_private_id), now, now))
        return self.afdian_account(owner) or values

    def create_afdian_oauth_state(self, user_id: str, state: str, redirect_uri: str, ttl_seconds: int = 600) -> dict[str, Any]:
        expires = _iso(_now() + timedelta(seconds=ttl_seconds))
        if self._is_supabase:
            self.db.client.table("afdian_oauth_states").insert({"state": state, "user_id": self._owner(user_id), "redirect_uri": redirect_uri, "expires_at": expires}).execute()
        else:
            self._execute("INSERT INTO afdian_oauth_states (state, user_id, redirect_uri, expires_at) VALUES (?, ?, ?, ?)", (state, self._owner(user_id), redirect_uri, expires))
        return {"state": state, "expires_at": expires}

    def consume_afdian_oauth_state(self, state: str) -> dict[str, Any] | None:
        row = self._query("SELECT * FROM afdian_oauth_states WHERE state = ?", (state,))
        if not row or row.get("consumed_at") or _parse(row["expires_at"]) <= _now():
            return None
        now = _iso(_now())
        if self._is_supabase:
            self.db.client.table("afdian_oauth_states").update({"consumed_at": now}).eq("state", state).is_("consumed_at", "null").execute()
        else:
            self._execute("UPDATE afdian_oauth_states SET consumed_at = ? WHERE state = ? AND consumed_at IS NULL", (now, state))
        return row

    def create_afdian_checkout(self, user_id: str, plan: str, plan_id: str, checkout_url: str, ttl_seconds: int = 1800) -> dict[str, Any]:
        if plan not in ("lite", "pro", "ultimate"):
            raise ValueError("暂不支持购买该会员档位")
        if not self.afdian_account(user_id):
            raise ValueError("请先绑定爱发电账号")
        session = {"id": str(uuid.uuid4()), "user_id": self._owner(user_id), "plan": plan, "plan_id": plan_id, "status": "pending", "checkout_url": checkout_url, "created_at": _iso(_now()), "expires_at": _iso(_now() + timedelta(seconds=ttl_seconds))}
        if self._is_supabase:
            self.db.client.table("afdian_checkout_sessions").insert(session).execute()
        else:
            self._execute("INSERT INTO afdian_checkout_sessions (id, user_id, plan, plan_id, status, checkout_url, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(session.values()))
        return session

    def afdian_checkout(self, user_id: str, checkout_id: str) -> dict[str, Any] | None:
        row = self._query("SELECT * FROM afdian_checkout_sessions WHERE id = ? AND user_id = ?", (checkout_id, self._owner(user_id)))
        if row and row["status"] == "pending" and _parse(row["expires_at"]) <= _now():
            row["status"] = "expired"
        return row

    def add_payment_review(self, out_trade_no: str | None, reason: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        item = {"id": str(uuid.uuid4()), "out_trade_no": out_trade_no, "reason": reason, "status": "open", "metadata": json.dumps(metadata or {}, ensure_ascii=False), "created_at": _iso(_now())}
        if self._is_supabase:
            item["metadata"] = metadata or {}
            self.db.client.table("membership_payment_reviews").insert(item).execute()
        else:
            self._execute("INSERT INTO membership_payment_reviews (id, out_trade_no, reason, status, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)", tuple(item.values()))
        return item

    def record_afdian_order(self, order: dict[str, Any], *, user_id: str, plan: str, verification_status: str = "verified", review_reason: str | None = None) -> bool:
        trade = str(order.get("out_trade_no") or "")
        if not trade:
            raise ValueError("缺少爱发电订单号")
        existing = self._query("SELECT * FROM afdian_orders WHERE out_trade_no = ?", (trade,))
        if existing:
            return False
        now = _iso(_now())
        values = (trade, self._owner(user_id), str(order.get("user_id") or ""), str(order.get("user_private_id") or ""), plan, str(order.get("plan_id") or ""), max(1, int(order.get("month") or 1)), float(order.get("total_amount") or 0), int(order.get("status") or 0), json.dumps(order, ensure_ascii=False), verification_status, review_reason, now, now)
        if self._is_supabase:
            self.db.client.table("afdian_orders").insert({"out_trade_no": values[0], "user_id": values[1], "afdian_user_id": values[2], "afdian_user_private_id": values[3], "plan": values[4], "plan_id": values[5], "month": values[6], "total_amount": values[7], "status": values[8], "raw_payload": order, "verification_status": values[10], "review_reason": values[11]}).execute()
        else:
            self._execute("INSERT INTO afdian_orders (out_trade_no, user_id, afdian_user_id, afdian_user_private_id, plan, plan_id, month, total_amount, status, raw_payload, verification_status, review_reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        return True

    def grant_afdian_order(self, order: dict[str, Any], *, user_id: str, plan: str) -> dict[str, Any]:
        trade = str(order["out_trade_no"])
        existing = self._query("SELECT * FROM membership_grants WHERE out_trade_no = ?", (trade,))
        if existing:
            return self.membership(user_id)
        now = _now()
        current = self.membership(self._owner(user_id))
        current_end = _parse(current["period_end"])
        base = current_end if current_end > now else now
        days = max(1, int(order.get("month") or 1)) * 31
        new_end = base + timedelta(days=days)
        rank = {"free": 0, "lite": 1, "pro": 2, "ultimate": 3, "enterprise": 4}
        effective_plan = plan if rank.get(plan, 0) >= rank.get(str(current["plan"]), 0) or current_end <= now else str(current["plan"])
        policy = POLICIES[effective_plan]
        grant = {"id": str(uuid.uuid4()), "out_trade_no": trade, "user_id": self._owner(user_id), "plan": plan, "starts_at": _iso(now), "ends_at": _iso(new_end), "created_at": _iso(now)}
        if self._is_supabase:
            self.db.client.table("membership_grants").insert(grant).execute()
            self.db.client.table("memberships").update({"plan": effective_plan, "status": "active", "period_end": _iso(new_end), "price_rmb": policy.price_rmb, "monthly_cost_limit_rmb": policy.monthly_cost_limit_rmb, "updated_at": _iso(now)}).eq("user_id", self._owner(user_id)).execute()
            self.db.client.table("afdian_checkout_sessions").update({"status": "paid", "completed_at": _iso(now)}).eq("user_id", self._owner(user_id)).eq("plan", plan).eq("status", "pending").execute()
        else:
            self._execute("INSERT INTO membership_grants (id, out_trade_no, user_id, plan, starts_at, ends_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(grant.values()))
            self._execute("UPDATE memberships SET plan = ?, status = 'active', period_end = ?, price_rmb = ?, monthly_cost_limit_rmb = ?, updated_at = ? WHERE user_id = ?", (effective_plan, _iso(new_end), policy.price_rmb, policy.monthly_cost_limit_rmb, _iso(now), self._owner(user_id)))
            self._execute("UPDATE afdian_checkout_sessions SET status = 'paid', completed_at = ? WHERE user_id = ? AND plan = ? AND status = 'pending'", (_iso(now), self._owner(user_id), plan))
        return self.membership(user_id)
