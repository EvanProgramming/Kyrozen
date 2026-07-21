"""Adaptive question engine for problem discovery.

The engine decides which dimension to explore next based on what is still
missing from the current Problem Brief. It never asks more than one or two
focused follow-up questions at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .brief import ProblemBrief


DIMENSIONS = [
    "target_user",
    "scenario",
    "surface_problem",
    "deep_need",
    "current_solution",
    "current_solution_problem",
    "frequency",
    "impact",
]


DIMENSION_QUESTIONS: dict[str, list[str]] = {
    "target_user": [
        "谁会遇到这个问题？能描述一下这个人吗（身份、年龄、习惯等）？",
        "这个问题主要影响哪类人？",
    ],
    "scenario": [
        "这个问题通常发生在什么场景？比如时间、地点、环境？",
        "能描述一次你最近遇到这个问题的具体情况吗？",
    ],
    "surface_problem": [
        "具体发生了什么让你觉得不舒服/不方便？",
        "如果用一句话描述你遇到的最大困难，会是什么？",
    ],
    "deep_need": [
        "如果这个问题被完美解决，对你来说最重要的是什么？",
        "除了表面的不方便，你真正想要达到的状态是什么？",
    ],
    "current_solution": [
        "你现在是怎么处理这个问题的？",
        "你目前用什么方法或工具来应对？",
    ],
    "current_solution_problem": [
        "现在的解决方法有什么不好？",
        "用现在的方案时，最让你烦恼的一步是什么？",
    ],
    "frequency": [
        "这个问题多久出现一次？",
        "是每天都会遇到，还是偶尔？",
    ],
    "impact": [
        "这个问题对你影响大吗？影响的是什么方面？",
        "如果不解决这个问题，会带来什么后果？",
    ],
}


@dataclass
class NextQuestion:
    """A single recommended next question for the user."""

    dimension: str
    question: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "question": self.question,
            "reason": self.reason,
        }


class QuestionEngine:
    """Select the next question to fill the most important missing dimension."""

    # Order of priority when exploring a new problem
    PRIORITY = [
        "surface_problem",
        "scenario",
        "target_user",
        "current_solution",
        "current_solution_problem",
        "deep_need",
        "frequency",
        "impact",
    ]

    def find_missing_dimensions(self, brief: ProblemBrief) -> list[str]:
        """Return dimensions that are still empty, ordered by priority."""
        values: dict[str, str] = {
            "target_user": brief.target_user,
            "scenario": brief.scenario,
            "surface_problem": brief.surface_problem,
            "deep_need": brief.deep_need,
            "current_solution": brief.current_solution,
            "current_solution_problem": brief.current_solution_problem,
            "frequency": brief.frequency,
            "impact": brief.impact,
        }
        missing = [dim for dim in self.PRIORITY if not values.get(dim, "").strip()]
        return missing

    def next_question(self, brief: ProblemBrief) -> NextQuestion | None:
        """Pick the highest-priority missing dimension and return a question."""
        missing = self.find_missing_dimensions(brief)
        if not missing:
            return None
        dimension = missing[0]
        questions = DIMENSION_QUESTIONS.get(dimension, [])
        if not questions:
            return None
        # Deterministically pick the first question for the dimension
        question = questions[0]
        reason = f"Missing dimension: {dimension}"
        return NextQuestion(dimension=dimension, question=question, reason=reason)

    def state_summary(self, brief: ProblemBrief) -> dict[str, Any]:
        """Return a summary of filled/missing dimensions for UI display."""
        missing = self.find_missing_dimensions(brief)
        filled = [dim for dim in self.PRIORITY if dim not in missing]
        next_q = self.next_question(brief)
        return {
            "filled_dimensions": filled,
            "missing_dimensions": missing,
            "next_question": next_q.to_dict() if next_q else None,
        }
