"""Deterministic multi-provider research runs with bounded retries."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .models import ResearchSource
from kyrozen.tools.research.base import SearchProvider


@dataclass
class ResearchRun:
    query: str
    run_id: str
    status: str = "pending"
    attempts: int = 0
    provider_status: dict[str, str] = field(default_factory=dict)
    provider_attempts: dict[str, int] = field(default_factory=dict)
    retry_queue: list[dict[str, Any]] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "status": self.status,
            "attempts": self.attempts,
            "provider_status": dict(self.provider_status),
            "provider_attempts": dict(self.provider_attempts),
            "retry_queue": list(self.retry_queue),
            "sources": [source.to_dict() for source in self.sources],
            "errors": dict(self.errors),
        }


def execute_research_run(
    query: str,
    providers: list[SearchProvider],
    *,
    run_id: str,
    limit: int = 5,
    max_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ResearchRun:
    """Run each provider independently; one failure never blocks others."""
    run = ResearchRun(query=query, run_id=run_id, status="running")
    for provider in providers:
        name = getattr(provider, "name", provider.__class__.__name__)
        provider_attempts = 0
        result: list[ResearchSource] = []
        while provider_attempts < max_attempts:
            provider_attempts += 1
            run.attempts += 1
            try:
                result = provider.search(query, limit=limit)
            except Exception as exc:
                # A third-party adapter must never abort the project-wide run.
                # Convert unexpected adapter failures into the same durable
                # retryable record used by HTTP failures.
                source_type = str(getattr(provider, "source_type", "web_page"))
                result = [ResearchSource(
                    title=f"{name} search failed",
                    source_type=source_type,
                    summary=f"{type(exc).__name__}: {exc}",
                    confidence="low",
                    fact_type="unknown",
                )]
            run.provider_attempts[name] = provider_attempts
            rate_limited = any("rate limited" in source.title.lower() for source in result)
            failed = any(" search failed" in source.title.lower() for source in result)
            retryable = rate_limited or failed
            if retryable and provider_attempts < max_attempts:
                backoff_seconds = min(2 ** (provider_attempts - 1), 30)
                run.provider_status[name] = "retrying"
                run.retry_queue.append({
                    "provider": name,
                    "attempt": provider_attempts,
                    "status": "queued",
                    "backoff_seconds": backoff_seconds,
                    "reason": "rate_limited" if rate_limited else "transient_failure",
                })
                # Do not immediately hammer a provider after a 429 or
                # transient failure. The sleeper is injectable for tests.
                sleep_fn(backoff_seconds)
            if result and not retryable:
                break
        if not result:
            run.provider_status[name] = "failed"
            run.errors[name] = "Provider returned no results"
        elif any("not configured" in source.title.lower() for source in result):
            run.provider_status[name] = "unconfigured"
        elif any("rate limited" in source.title.lower() for source in result):
            run.provider_status[name] = "rate_limited"
        elif any("failed" in source.title.lower() for source in result):
            run.provider_status[name] = "failed"
            run.errors[name] = result[0].summary
        else:
            run.provider_status[name] = "success"
            run.sources.extend(result)
    run.status = "completed" if any(status == "success" for status in run.provider_status.values()) else "blocked"
    return run
