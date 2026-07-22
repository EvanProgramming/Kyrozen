"""Runtime state for Market Research sessions.

A ResearchSession tracks the current research plan, collected sources,
competitors, and progress indicators for a single project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Competitor, MarketGap, MarketResearchReport, ResearchPlan, ResearchSource


RESEARCH_STAGES = [
    "understanding_problem",
    "planning_research",
    "searching_sources",
    "analyzing_competitors",
    "reviewing_feedback",
    "generating_report",
    "completed",
]


@dataclass
class ResearchSession:
    """Runtime state for market research on a single project."""

    project_id: str
    stage: str = "understanding_problem"
    plan: ResearchPlan = field(default_factory=ResearchPlan)
    sources: list[ResearchSource] = field(default_factory=list)
    competitors: list[Competitor] = field(default_factory=list)
    feedback: list[ResearchSource] = field(default_factory=list)
    alternatives: list[ResearchSource] = field(default_factory=list)
    market_gap: MarketGap = field(default_factory=MarketGap)
    report: MarketResearchReport = field(default_factory=MarketResearchReport)
    logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage not in RESEARCH_STAGES:
            raise ValueError(f"Invalid research stage '{self.stage}'")

    def set_stage(self, stage: str) -> None:
        """Move to the next research stage and log it."""
        if stage not in RESEARCH_STAGES:
            raise ValueError(f"Invalid research stage '{stage}'")
        self.stage = stage
        self.logs.append(f"Stage: {stage}")
        if len(self.logs) > 50:
            self.logs = self.logs[-50:]

    def add_source(self, source: ResearchSource) -> None:
        """Add a source if its URL is not already recorded."""
        existing_urls = {s.url for s in self.sources}
        if source.url and source.url not in existing_urls:
            self.sources.append(source)

    def add_competitor(self, competitor: Competitor) -> None:
        """Add a competitor if its name is not already recorded."""
        existing_names = {c.name.lower() for c in self.competitors}
        if competitor.name and competitor.name.lower() not in existing_names:
            self.competitors.append(competitor)

    def add_feedback(self, source: ResearchSource) -> None:
        """Add a community feedback source."""
        existing_urls = {s.url for s in self.feedback}
        if source.url and source.url not in existing_urls:
            self.feedback.append(source)

    def update_report(self, report: MarketResearchReport) -> None:
        """Replace the current report draft."""
        self.report = report

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "plan": self.plan.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "competitors": [c.to_dict() for c in self.competitors],
            "feedback": [s.to_dict() for s in self.feedback],
            "alternatives": [s.to_dict() for s in self.alternatives],
            "market_gap": self.market_gap.to_dict(),
            "report": self.report.to_dict(),
            "logs": list(self.logs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchSession":
        return cls(
            project_id=data.get("project_id", ""),
            stage=data.get("stage", "understanding_problem"),
            plan=ResearchPlan.from_dict(data.get("plan") or {}),
            sources=[ResearchSource.from_dict(s) for s in data.get("sources") or []],
            competitors=[Competitor.from_dict(c) for c in data.get("competitors") or []],
            feedback=[ResearchSource.from_dict(s) for s in data.get("feedback") or []],
            alternatives=[ResearchSource.from_dict(s) for s in data.get("alternatives") or []],
            market_gap=MarketGap.from_dict(data.get("market_gap") or {}),
            report=MarketResearchReport.from_dict(data.get("report") or {}),
            logs=list(data.get("logs") or []),
        )
