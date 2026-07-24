"""Data models for Kyrozen Phase 4 Market Research.

These models capture research plans, sources, competitors, market gaps, and the
final Market Research Report artifact. They are intentionally separate from the
Problem Brief models in kyrozen.discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CONFIDENCE_LEVELS = {"low", "medium", "high"}
FACT_TYPES = {"fact", "inference", "unknown"}
SOURCE_TYPES = {
    "product",
    "app",
    "github",
    "paper",
    "patent",
    "community",
    "crowdfunding",
    "diy",
    "alternative",
    "web_page",
}

OPPORTUNITY_DECISIONS = {
    "continue_development",
    "narrow_scope",
    "change_target_user",
    "change_product_form",
    "use_existing_solution",
    "pause",
    "abandon",
}


def _today_iso() -> str:
    """Return today's date as an ISO 8601 string."""
    from datetime import date

    return date.today().isoformat()


@dataclass
class ResearchPlan:
    """A single research direction derived from the Problem Brief."""

    research_question: str = ""
    search_directions: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_question": self.research_question,
            "search_directions": list(self.search_directions),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchPlan":
        return cls(
            research_question=data.get("research_question", ""),
            search_directions=list(data.get("search_directions") or []),
            reason=data.get("reason", ""),
        )


@dataclass
class ResearchSource:
    """One external source collected during market research.

    Every source must record provenance and whether its claim is a fact,
    an AI inference, or unknown.
    """

    title: str = ""
    url: str = ""
    source_type: str = "web_page"  # product/app/github/paper/patent/community/...
    publish_date: str = ""
    access_date: str = field(default_factory=_today_iso)
    summary: str = ""
    related_claim: str = ""  # the claim this source supports or refutes
    confidence: str = "medium"  # low/medium/high
    fact_type: str = "fact"  # fact/inference/unknown

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"Invalid source_type '{self.source_type}'")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")
        if self.fact_type not in FACT_TYPES:
            raise ValueError(f"Invalid fact_type '{self.fact_type}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source_type": self.source_type,
            "publish_date": self.publish_date,
            "access_date": self.access_date,
            "summary": self.summary,
            "related_claim": self.related_claim,
            "confidence": self.confidence,
            "fact_type": self.fact_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchSource":
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            source_type=data.get("source_type", "web_page"),
            publish_date=data.get("publish_date", ""),
            access_date=data.get("access_date", _today_iso()),
            summary=data.get("summary", ""),
            related_claim=data.get("related_claim", ""),
            confidence=data.get("confidence", "medium"),
            fact_type=data.get("fact_type", "fact"),
        )


@dataclass
class Competitor:
    """Structured analysis of one competitor or existing solution."""

    name: str = ""
    company: str = ""
    solution: str = ""
    target_user: str = ""
    main_features: list[str] = field(default_factory=list)
    price: str = ""
    advantages: list[str] = field(default_factory=list)
    complaints: list[str] = field(default_factory=list)
    failure_reason: str = ""
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "company": self.company,
            "solution": self.solution,
            "target_user": self.target_user,
            "main_features": list(self.main_features),
            "price": self.price,
            "advantages": list(self.advantages),
            "complaints": list(self.complaints),
            "failure_reason": self.failure_reason,
            "sources": list(self.sources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Competitor":
        return cls(
            name=data.get("name", ""),
            company=data.get("company", ""),
            solution=data.get("solution", ""),
            target_user=data.get("target_user", ""),
            main_features=list(data.get("main_features") or []),
            price=data.get("price", ""),
            advantages=list(data.get("advantages") or []),
            complaints=list(data.get("complaints") or []),
            failure_reason=data.get("failure_reason", ""),
            sources=list(data.get("sources") or []),
        )


@dataclass
class MarketGap:
    """Analysis of the remaining opportunity after reviewing existing solutions."""

    existing_solution: str = ""
    problem_remaining: str = ""
    possible_difference: str = ""
    risk: str = ""
    confidence: str = "low"

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Invalid confidence '{self.confidence}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "existing_solution": self.existing_solution,
            "problem_remaining": self.problem_remaining,
            "possible_difference": self.possible_difference,
            "risk": self.risk,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketGap":
        return cls(
            existing_solution=data.get("existing_solution", ""),
            problem_remaining=data.get("problem_remaining", ""),
            possible_difference=data.get("possible_difference", ""),
            risk=data.get("risk", ""),
            confidence=data.get("confidence", "low"),
        )


@dataclass
class MarketResearchReport:
    """Final artifact produced by the Market Research Agent."""

    problem_summary: str = ""
    market_status: str = ""
    competitors: list[Competitor] = field(default_factory=list)
    open_source_projects: list[ResearchSource] = field(default_factory=list)
    user_feedback: list[ResearchSource] = field(default_factory=list)
    alternative_solutions: list[ResearchSource] = field(default_factory=list)
    technology_routes: list[str] = field(default_factory=list)
    market_gap: MarketGap = field(default_factory=MarketGap)
    risks: list[str] = field(default_factory=list)
    recommendation: str = "pause"  # one of OPPORTUNITY_DECISIONS
    sources: list[ResearchSource] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.recommendation not in OPPORTUNITY_DECISIONS:
            raise ValueError(f"Invalid recommendation '{self.recommendation}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_summary": self.problem_summary,
            "market_status": self.market_status,
            "competitors": [c.to_dict() for c in self.competitors],
            "open_source_projects": [s.to_dict() for s in self.open_source_projects],
            "user_feedback": [s.to_dict() for s in self.user_feedback],
            "alternative_solutions": [s.to_dict() for s in self.alternative_solutions],
            "technology_routes": list(self.technology_routes),
            "market_gap": self.market_gap.to_dict(),
            "risks": list(self.risks),
            "recommendation": self.recommendation,
            "sources": [s.to_dict() for s in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketResearchReport":
        # Support both the canonical schema and the looser schema produced by
        # earlier agent prompts (e.g. market_size_and_trends, competitor_analysis).
        market_status = data.get("market_status", "")
        if not market_status and data.get("market_size_and_trends"):
            market_status = data["market_size_and_trends"]

        competitors: list[Competitor] = []
        for c in data.get("competitors") or []:
            competitors.append(Competitor.from_dict(c))
        for c in data.get("competitor_analysis") or []:
            competitors.append(
                Competitor(
                    name=c.get("name", ""),
                    company=c.get("type", ""),
                    solution=c.get("gap_analysis", ""),
                    target_user="",
                    main_features=[],
                    price=c.get("price", ""),
                    advantages=[c.get("strengths", "")] if c.get("strengths") else [],
                    complaints=[c.get("weaknesses", "")] if c.get("weaknesses") else [],
                    failure_reason="",
                    sources=[c.get("source_url", "")] if c.get("source_url") else [],
                )
            )

        user_feedback: list[ResearchSource] = [
            ResearchSource.from_dict(s) for s in data.get("user_feedback") or []
        ]
        for item in data.get("user_pain_points_analysis") or []:
            user_feedback.append(
                ResearchSource(
                    title=f"Pain point: {item.get('pain_point', '')}",
                    url=item.get("source_url", ""),
                    source_type="community",
                    summary=item.get("evidence", ""),
                    related_claim=item.get("pain_point", ""),
                    confidence="medium",
                    fact_type="fact",
                )
            )

        alternative_solutions: list[ResearchSource] = [
            ResearchSource.from_dict(s) for s in data.get("alternative_solutions") or []
        ]
        if data.get("existing_solutions_adequacy"):
            alternative_solutions.append(
                ResearchSource(
                    title="Existing solutions adequacy",
                    summary=data["existing_solutions_adequacy"],
                    related_claim="Assessment of existing solutions",
                    source_type="web_page",
                )
            )

        market_gap = MarketGap.from_dict(data.get("market_gap") or {})
        if data.get("opportunity_assessment"):
            market_gap.possible_difference = data["opportunity_assessment"]
        if data.get("overall_confidence") in CONFIDENCE_LEVELS:
            market_gap.confidence = data["overall_confidence"]

        risks = list(data.get("risks") or [])
        for unknown in data.get("key_unknowns") or []:
            risks.append(f"Unknown: {unknown}")

        problem_summary = data.get("problem_summary", "")
        if not problem_summary and data.get("existing_solutions_adequacy"):
            problem_summary = data["existing_solutions_adequacy"]

        return cls(
            problem_summary=problem_summary,
            market_status=market_status,
            competitors=competitors,
            open_source_projects=[
                ResearchSource.from_dict(s) for s in data.get("open_source_projects") or []
            ],
            user_feedback=user_feedback,
            alternative_solutions=alternative_solutions,
            technology_routes=list(data.get("technology_routes") or []),
            market_gap=market_gap,
            risks=risks,
            recommendation=data.get("recommendation", "pause"),
            sources=[ResearchSource.from_dict(s) for s in data.get("sources") or []],
        )
