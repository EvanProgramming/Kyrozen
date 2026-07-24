"""Data models for Kyrozen Phase 5 Product Planning.

These models capture product goals, target users, features, MVP scope,
solution alternatives, and the final Product Brief and PRD artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PRIORITY_LEVELS = {"Must Have", "Should Have", "Could Have", "Not Now"}

PRODUCT_DECISIONS = {
    "continue_with_solution",
    "pivot_solution",
    "narrow_scope",
    "expand_scope",
    "pause",
    "abandon",
}

COMPARISON_DIMENSIONS = {
    "solves_problem",
    "cost",
    "difficulty",
    "development_time",
    "usage_barrier",
    "stability",
    "scalability",
    "risk",
}


@dataclass
class ProductGoal:
    """High-level goal of the product."""

    product_goal: str = ""
    target_user: str = ""
    core_problem: str = ""
    value_proposition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_goal": self.product_goal,
            "target_user": self.target_user,
            "core_problem": self.core_problem,
            "value_proposition": self.value_proposition,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductGoal":
        return cls(
            product_goal=data.get("product_goal", ""),
            target_user=data.get("target_user", ""),
            core_problem=data.get("core_problem", ""),
            value_proposition=data.get("value_proposition", ""),
        )


@dataclass
class TargetUser:
    """Concrete description of the target user."""

    primary_user: str = ""
    secondary_user: str = ""
    use_case: str = ""
    user_context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_user": self.primary_user,
            "secondary_user": self.secondary_user,
            "use_case": self.use_case,
            "user_context": self.user_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TargetUser":
        return cls(
            primary_user=data.get("primary_user", ""),
            secondary_user=data.get("secondary_user", ""),
            use_case=data.get("use_case", ""),
            user_context=data.get("user_context", ""),
        )


@dataclass
class UserJourney:
    """Before / During / After user experience."""

    before: str = ""
    during: str = ""
    after: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"before": self.before, "during": self.during, "after": self.after}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserJourney":
        return cls(
            before=data.get("before", ""),
            during=data.get("during", ""),
            after=data.get("after", ""),
        )


@dataclass
class Feature:
    """One product feature with priority."""

    name: str = ""
    description: str = ""
    user_problem: str = ""
    priority: str = "Could Have"  # Must Have / Should Have / Could Have / Not Now

    def __post_init__(self) -> None:
        normalized = self._normalize_priority(self.priority)
        if normalized is None:
            raise ValueError(f"Invalid priority '{self.priority}'")
        object.__setattr__(self, "priority", normalized)

    @staticmethod
    def _normalize_priority(value: str) -> str | None:
        value = (value or "").strip()
        if value in PRIORITY_LEVELS:
            return value
        lower = value.lower()
        mapping = {
            "p0": "Must Have",
            "must": "Must Have",
            "must have": "Must Have",
            "high": "Must Have",
            "高": "Must Have",
            "必须": "Must Have",
            "p1": "Should Have",
            "should": "Should Have",
            "should have": "Should Have",
            "medium": "Should Have",
            "中": "Should Have",
            "建议": "Should Have",
            "p2": "Could Have",
            "could": "Could Have",
            "could have": "Could Have",
            "low": "Could Have",
            "低": "Could Have",
            "可选": "Could Have",
            "p3": "Not Now",
            "not now": "Not Now",
            "won't": "Not Now",
            "wont": "Not Now",
            "later": "Not Now",
            "延后": "Not Now",
            "暂不": "Not Now",
        }
        return mapping.get(lower)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "user_problem": self.user_problem,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Feature":
        priority = data.get("priority", "Could Have")
        normalized = cls._normalize_priority(priority)
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            user_problem=data.get("user_problem", ""),
            priority=normalized if normalized is not None else "Could Have",
        )


@dataclass
class MVP:
    """Minimum Viable Product scope."""

    mvp_features: list[str] = field(default_factory=list)
    excluded_features: list[str] = field(default_factory=list)
    success_metric: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mvp_features": list(self.mvp_features),
            "excluded_features": list(self.excluded_features),
            "success_metric": self.success_metric,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MVP":
        return cls(
            mvp_features=list(data.get("mvp_features") or []),
            excluded_features=list(data.get("excluded_features") or []),
            success_metric=data.get("success_metric", ""),
        )


@dataclass
class Solution:
    """One candidate solution for solving the problem."""

    name: str = ""
    solution: str = ""
    advantages: list[str] = field(default_factory=list)
    disadvantages: list[str] = field(default_factory=list)
    cost: str = ""
    difficulty: str = ""
    development_time: str = ""
    risk: str = ""
    scalability: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "solution": self.solution,
            "advantages": list(self.advantages),
            "disadvantages": list(self.disadvantages),
            "cost": self.cost,
            "difficulty": self.difficulty,
            "development_time": self.development_time,
            "risk": self.risk,
            "scalability": self.scalability,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Solution":
        return cls(
            name=data.get("name", ""),
            solution=data.get("solution", ""),
            advantages=list(data.get("advantages") or []),
            disadvantages=list(data.get("disadvantages") or []),
            cost=data.get("cost", ""),
            difficulty=data.get("difficulty", ""),
            development_time=data.get("development_time", ""),
            risk=data.get("risk", ""),
            scalability=data.get("scalability", ""),
        )


@dataclass
class SolutionComparison:
    """Comparison of multiple candidate solutions."""

    solutions: list[Solution] = field(default_factory=list)
    comparison_dimensions: list[str] = field(default_factory=lambda: list(COMPARISON_DIMENSIONS))
    recommendation: str = ""
    recommendation_reason: str = ""

    def __post_init__(self) -> None:
        invalid = {d for d in self.comparison_dimensions if d not in COMPARISON_DIMENSIONS}
        if invalid:
            raise ValueError(f"Invalid comparison dimensions: {invalid}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "solutions": [s.to_dict() for s in self.solutions],
            "comparison_dimensions": list(self.comparison_dimensions),
            "recommendation": self.recommendation,
            "recommendation_reason": self.recommendation_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SolutionComparison":
        return cls(
            solutions=[Solution.from_dict(s) for s in data.get("solutions") or []],
            comparison_dimensions=list(data.get("comparison_dimensions") or COMPARISON_DIMENSIONS),
            recommendation=data.get("recommendation", ""),
            recommendation_reason=data.get("recommendation_reason", ""),
        )


@dataclass
class ProductBrief:
    """High-level product brief artifact."""

    product_goal: ProductGoal = field(default_factory=ProductGoal)
    target_user: TargetUser = field(default_factory=TargetUser)
    user_journey: UserJourney = field(default_factory=UserJourney)
    value_proposition: str = ""
    user_stories: list[str] = field(default_factory=list)
    core_features: list[Feature] = field(default_factory=list)
    mvp_scope: MVP = field(default_factory=MVP)
    non_goals: list[str] = field(default_factory=list)
    success_metrics: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_goal": self.product_goal.to_dict(),
            "target_user": self.target_user.to_dict(),
            "user_journey": self.user_journey.to_dict(),
            "value_proposition": self.value_proposition,
            "user_stories": list(self.user_stories),
            "core_features": [f.to_dict() for f in self.core_features],
            "mvp_scope": self.mvp_scope.to_dict(),
            "non_goals": list(self.non_goals),
            "success_metrics": list(self.success_metrics),
            "constraints": list(self.constraints),
            "risks": list(self.risks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductBrief":
        # Support both the canonical schema and the looser schema often produced
        # by the agent (e.g. product_name, tagline, key_features, mvp_scope as
        # plain strings).
        product_goal = ProductGoal.from_dict(data.get("product_goal") or {})
        if not product_goal.product_goal:
            product_goal.product_goal = data.get("product_name", data.get("title", ""))
        if not product_goal.target_user:
            product_goal.target_user = data.get("target_user", "") if isinstance(data.get("target_user"), str) else ""
        if not product_goal.core_problem:
            product_goal.core_problem = data.get("problem", data.get("core_problem", ""))
        if not product_goal.value_proposition:
            product_goal.value_proposition = data.get("core_value_proposition", "")

        if isinstance(data.get("target_user"), str):
            target_user = TargetUser(primary_user=data["target_user"])
        else:
            target_user = TargetUser.from_dict(data.get("target_user") or {})

        value_proposition = data.get("value_proposition", "")
        if not value_proposition:
            value_proposition = data.get("tagline", data.get("slogan", ""))

        core_features: list[Feature] = []
        for f in data.get("core_features") or []:
            if isinstance(f, str):
                core_features.append(Feature(name=f, description=f, priority="Must Have"))
            elif isinstance(f, dict):
                core_features.append(Feature.from_dict(f))
        if not core_features:
            for i, name in enumerate(data.get("key_features") or []):
                priority = "Must Have" if i < 3 else "Should Have"
                core_features.append(Feature(name=name, description=name, priority=priority))

        if isinstance(data.get("mvp_scope"), list):
            mvp_scope = MVP(mvp_features=[str(x) for x in data["mvp_scope"]])
        else:
            mvp_scope = MVP.from_dict(data.get("mvp_scope") or {})
        if not mvp_scope.success_metric and data.get("success_metrics"):
            mvp_scope.success_metric = str(data["success_metrics"][0])

        success_metrics = list(data.get("success_metrics") or [])
        risks = list(data.get("risks") or [])
        if data.get("monetization_model"):
            risks.append(f"Monetization: {data['monetization_model']}")
        if data.get("differentiation"):
            value_proposition = f"{value_proposition}\nDifferentiation: {data['differentiation']}".strip()

        return cls(
            product_goal=product_goal,
            target_user=target_user,
            user_journey=UserJourney.from_dict(data.get("user_journey") or {}),
            value_proposition=value_proposition,
            user_stories=list(data.get("user_stories") or []),
            core_features=core_features,
            mvp_scope=mvp_scope,
            non_goals=list(data.get("non_goals") or []),
            success_metrics=success_metrics,
            constraints=list(data.get("constraints") or []),
            risks=risks,
        )


@dataclass
class PRD:
    """Product Requirements Document artifact."""

    overview: str = ""
    user_stories: list[str] = field(default_factory=list)
    functional_requirements: list[str] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    mvp_scope: MVP = field(default_factory=MVP)
    out_of_scope: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overview": self.overview,
            "user_stories": list(self.user_stories),
            "functional_requirements": list(self.functional_requirements),
            "non_functional_requirements": list(self.non_functional_requirements),
            "mvp_scope": self.mvp_scope.to_dict(),
            "out_of_scope": list(self.out_of_scope),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PRD":
        return cls(
            overview=data.get("overview", ""),
            user_stories=list(data.get("user_stories") or []),
            functional_requirements=list(data.get("functional_requirements") or []),
            non_functional_requirements=list(data.get("non_functional_requirements") or []),
            mvp_scope=MVP.from_dict(data.get("mvp_scope") or {}),
            out_of_scope=list(data.get("out_of_scope") or []),
        )
