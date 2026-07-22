"""Proactive suggestion generation for Kyrozen Phase 9."""

from __future__ import annotations

import json
from typing import Any

from .models import Suggestion

from .repository import LearningRepository

if True:  # typing-only guard for circular imports
    from kyrozen.project.manager import ProjectManager


class SuggestionGenerator:
    """Analyze project artifacts and generate improvement suggestions."""

    def __init__(
        self,
        project_manager: ProjectManager | None = None,
        memory: LearningRepository | None = None,
    ) -> None:
        self.project_manager = project_manager
        self.memory = memory

    def analyze(self, project_id: str) -> list[Suggestion]:
        """Run all heuristic detectors and return new suggestions."""
        if self.project_manager is None:
            return []

        suggestions: list[Suggestion] = []
        suggestions.extend(self._detect_test_gaps(project_id))
        suggestions.extend(self._detect_scope_drift(project_id))
        suggestions.extend(self._detect_unverified_assumptions(project_id))
        suggestions.extend(self._detect_cost_optimization(project_id))
        suggestions.extend(self._detect_tech_risk(project_id))
        suggestions.extend(self._detect_cross_project_learning(project_id))
        return suggestions

    def _load_artifacts(self, project_id: str, artifact_type: str) -> list[dict[str, Any]]:
        """Load artifacts of a specific type and parse JSON content."""
        artifacts = []
        if self.project_manager is None:
            return artifacts
        for artifact in self.project_manager.list_artifacts(project_id):
            if artifact.type != artifact_type:
                continue
            try:
                artifacts.append(json.loads(artifact.content))
            except (json.JSONDecodeError, ValueError):
                continue
        return artifacts

    def _detect_test_gaps(self, project_id: str) -> list[Suggestion]:
        """Find PRD requirements without corresponding test cases."""
        prds = self._load_artifacts(project_id, "prd")
        test_plans = self._load_artifacts(project_id, "test_plan")

        requirements: set[str] = set()
        for prd in prds:
            for req in prd.get("functional_requirements", []) + prd.get("non_functional_requirements", []):
                requirements.add(req)

        covered: set[str] = set()
        for plan in test_plans:
            for case in plan.get("test_cases", []):
                related = case.get("related_requirement", "")
                if related:
                    covered.add(related)

        gaps = []
        for req in requirements:
            if req not in covered:
                gaps.append(req)

        if not gaps:
            return []

        return [
            Suggestion(
                suggestion=f"为 {len(gaps)} 条需求补充测试用例",
                reason="PRD 中的部分需求没有对应测试用例，可能导致验证遗漏。",
                source_project_id=project_id,
                evidence=gaps[:5],
                impact="提高测试覆盖率，降低发布风险",
                priority="high" if len(gaps) > 3 else "medium",
                status="new",
                category="test_gap",
            )
        ]

    def _detect_scope_drift(self, project_id: str) -> list[Suggestion]:
        """Detect when current work touches PRD out-of-scope items."""
        prds = self._load_artifacts(project_id, "prd")
        iterations = self._load_artifacts(project_id, "iteration_plan")

        out_of_scope: set[str] = set()
        for prd in prds:
            out_of_scope.update(prd.get("out_of_scope", []))
        if not out_of_scope:
            return []

        drift_targets: list[str] = []
        for iteration in iterations:
            for item in iteration.get("items", []):
                target = item.get("target", "")
                for scope_item in out_of_scope:
                    if scope_item.lower() in target.lower() or target.lower() in scope_item.lower():
                        drift_targets.append(target)

        if not drift_targets:
            return []

        return [
            Suggestion(
                suggestion="检查当前迭代是否偏离 PRD 范围",
                reason="迭代计划中出现了原本标记为 out-of-scope 的内容。",
                source_project_id=project_id,
                evidence=drift_targets[:5],
                impact="避免资源浪费在明确排除的功能上",
                priority="high",
                status="new",
                category="scope_drift",
            )
        ]

    def _detect_unverified_assumptions(self, project_id: str) -> list[Suggestion]:
        """Find requirements without user feedback."""
        prds = self._load_artifacts(project_id, "prd")
        feedbacks = self._load_artifacts(project_id, "user_feedback")

        requirements: list[str] = []
        for prd in prds:
            requirements.extend(prd.get("functional_requirements", []))

        if not requirements or feedbacks:
            return []

        return [
            Suggestion(
                suggestion="收集核心需求的用户验证反馈",
                reason="PRD 已定义功能需求，但尚未记录任何用户反馈。",
                source_project_id=project_id,
                evidence=requirements[:5],
                impact="避免开发出用户不需要的功能",
                priority="high",
                status="new",
                category="unverified_assumption",
            )
        ]

    def _detect_cost_optimization(self, project_id: str) -> list[Suggestion]:
        """Detect duplicate components in BOM."""
        boms = self._load_artifacts(project_id, "bom")
        if not boms:
            return []

        seen: dict[str, int] = {}
        for bom in boms:
            for item in bom.get("items", []):
                name = item.get("name", "")
                if name:
                    seen[name] = seen.get(name, 0) + 1

        duplicates = [name for name, count in seen.items() if count > 1]
        if not duplicates:
            return []

        return [
            Suggestion(
                suggestion="检查 BOM 中重复或功能重叠的元件",
                reason="BOM 中某些元件出现多次，可能存在合并或替代空间。",
                source_project_id=project_id,
                evidence=duplicates[:5],
                impact="降低硬件成本并简化供应链",
                priority="medium",
                status="new",
                category="cost_optimization",
            )
        ]

    def _detect_tech_risk(self, project_id: str) -> list[Suggestion]:
        """Detect high architectural complexity or untested critical features."""
        tech_plans = self._load_artifacts(project_id, "technical_plan")
        test_results = self._load_artifacts(project_id, "test_result")

        suggestions: list[Suggestion] = []

        for plan in tech_plans:
            dependencies = plan.get("dependencies", [])
            if len(dependencies) > 8:
                suggestions.append(
                    Suggestion(
                        suggestion="评估技术栈复杂度",
                        reason=f"Technical Plan 依赖项较多（{len(dependencies)} 个），可能增加维护难度。",
                        source_project_id=project_id,
                        evidence=dependencies[:8],
                        impact="简化架构，降低技术风险",
                        priority="medium",
                        status="new",
                        category="tech_risk",
                    )
                )

        failed_tests = [r for r in test_results if r.get("result") in ("failed", "error")]
        if failed_tests:
            critical = [
                r.get("test_case_name", "")
                for r in failed_tests[:3]
            ]
            suggestions.append(
                Suggestion(
                    suggestion="优先修复未通过的测试",
                    reason=f"当前有 {len(failed_tests)} 个测试未通过，可能影响核心功能。",
                    source_project_id=project_id,
                    evidence=critical,
                    impact="提高产品质量",
                    priority="high",
                    status="new",
                    category="tech_risk",
                )
            )

        return suggestions

    def _detect_cross_project_learning(self, project_id: str) -> list[Suggestion]:
        """Suggest validated successes and warn about known failures from other projects."""
        if self.memory is None:
            return []

        current_project = self.project_manager.get(project_id) if self.project_manager else None
        if current_project is None:
            return []

        query_text = current_project.description or current_project.goal or ""
        if not query_text:
            return []

        suggestions: list[Suggestion] = []
        for memory_type in ("validated_success", "validated_failure"):
            records = self.memory.query_cross_project_memory(
                query_text=query_text,
                memory_type=memory_type,
                scope="user",
                limit=5,
            )
            for data in records:
                source_project_id = data.get("source_project_id")
                if source_project_id == project_id:
                    continue
                record_id = data.get("id", "")

                if memory_type == "validated_success":
                    solution = data.get("solution", "")
                    goal = data.get("goal", "")
                    if not solution:
                        continue
                    suggestions.append(
                        Suggestion(
                            suggestion=f"参考过往项目的成功经验：{solution}",
                            reason=f"当前项目与过往项目目标 '{goal}' 相似，该方案已被验证。",
                            source_project_id=project_id,
                            evidence=[f"来源项目：{source_project_id}", solution],
                            impact="复用已验证方案，降低试错成本",
                            priority="medium",
                            status="new",
                            category="new_opportunity",
                            related_learning_ids=[record_id],
                        )
                    )
                else:
                    problem = data.get("problem", "")
                    solution = data.get("solution", "")
                    affected_scope = data.get("affected_scope", "")
                    if not problem:
                        continue
                    suggestions.append(
                        Suggestion(
                            suggestion=f"注意过往项目的失败经验：{problem}",
                            reason=f"当前项目与 '{affected_scope}' 场景相似，该问题在过往项目中已被验证。",
                            source_project_id=project_id,
                            evidence=[f"来源项目：{source_project_id}", problem, solution],
                            impact="提前规避已知风险，减少重复失败",
                            priority="high",
                            status="new",
                            category="new_opportunity",
                            related_learning_ids=[record_id],
                        )
                    )

        return suggestions
