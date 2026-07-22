"""Runtime state for Product Planning sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Feature, MVP, PRD, ProductBrief, Solution, SolutionComparison


PLANNING_STAGES = {
    "understanding_inputs",
    "defining_goal",
    "defining_user",
    "designing_journey",
    "defining_features",
    "defining_mvp",
    "generating_solutions",
    "comparing_solutions",
    "recording_decision",
    "completed",
}


@dataclass
class PlanningSession:
    """Tracks the state of one product planning conversation."""

    project_id: str
    stage: str = "understanding_inputs"
    product_brief: ProductBrief = field(default_factory=ProductBrief)
    prd: PRD = field(default_factory=PRD)
    solution_comparison: SolutionComparison = field(default_factory=SolutionComparison)
    logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage not in PLANNING_STAGES:
            raise ValueError(f"Invalid planning stage '{self.stage}'")

    def set_stage(self, stage: str) -> None:
        if stage not in PLANNING_STAGES:
            raise ValueError(f"Invalid planning stage '{stage}'")
        self.stage = stage
        self.logs.append(f"Stage: {stage}")

    def add_feature(self, feature: Feature) -> None:
        existing = {f.name.lower() for f in self.product_brief.core_features}
        if feature.name and feature.name.lower() not in existing:
            self.product_brief.core_features.append(feature)

    def set_mvp(self, mvp: MVP) -> None:
        self.product_brief.mvp_scope = mvp
        self.prd.mvp_scope = mvp

    def add_solution(self, solution: Solution) -> None:
        existing = {s.name.lower() for s in self.solution_comparison.solutions}
        if solution.name and solution.name.lower() not in existing:
            self.solution_comparison.solutions.append(solution)

    def set_solution_recommendation(self, name: str, reason: str) -> None:
        self.solution_comparison.recommendation = name
        self.solution_comparison.recommendation_reason = reason

    def update_product_brief(self, brief: ProductBrief) -> None:
        self.product_brief = brief

    def update_prd(self, prd: PRD) -> None:
        self.prd = prd

    def update_solution_comparison(self, comparison: SolutionComparison) -> None:
        self.solution_comparison = comparison

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "product_brief": self.product_brief.to_dict(),
            "prd": self.prd.to_dict(),
            "solution_comparison": self.solution_comparison.to_dict(),
            "logs": list(self.logs),
        }
