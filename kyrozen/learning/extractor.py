"""Rule-based learning extraction from project events."""

from __future__ import annotations

from typing import Any

from .models import (
    FailureKnowledge,
    LearningEvent,
    LearningRecord,
    SuccessKnowledge,
)


class LearningExtractor:
    """Extract reusable learning records from Phase 8 and earlier events."""

    def extract(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        """Return proposed records, failures, and successes without saving them."""
        handler = getattr(self, f"_handle_{event.event_type}", self._handle_unknown)
        return handler(event)

    def _handle_test_result(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        payload = event.payload
        result = payload.get("result", "")
        test_case_name = payload.get("test_case_name", "")
        related_requirement = payload.get("related_requirement", "")
        related_feature = payload.get("related_feature", "")
        errors = payload.get("errors", "")
        actual = payload.get("actual", "")
        environment = payload.get("environment", "")

        records: list[LearningRecord] = []
        failures: list[FailureKnowledge] = []
        successes: list[SuccessKnowledge] = []

        tags = []
        if related_feature:
            tags.append(related_feature)
        if related_requirement:
            tags.append("requirement")

        source = f"test_result:{event.artifact_id or test_case_name}"

        if result in ("failed", "error"):
            problem = f"测试失败: {test_case_name}" if test_case_name else "测试失败"
            cause = str(errors or actual or "原因未记录")
            failure = FailureKnowledge(
                problem=problem,
                cause=cause,
                solution="待验证修复后更新",
                affected_scope=environment or related_feature or "unknown",
                verification=f"重新运行 {test_case_name} 应通过",
                source_project_id=event.project_id,
                confidence="medium" if errors else "low",
                verification_status="experiment_verified" if errors else "unverified",
            )
            failures.append(failure)

            records.append(
                LearningRecord(
                    memory=f"{problem}。影响范围：{related_feature or '未指定'}。",
                    memory_type="validated_failure",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="experiment_verified",
                    scope="private",
                    tags=tags,
                )
            )
        elif result == "passed":
            goal = f"验证 {related_requirement or test_case_name}"
            solution = f"通过测试 {test_case_name}"
            success = SuccessKnowledge(
                goal=goal,
                solution=solution,
                conditions=[environment] if environment else [],
                result="测试通过",
                source_project_id=event.project_id,
                confidence="medium",
                verification_status="experiment_verified",
            )
            successes.append(success)

            records.append(
                LearningRecord(
                    memory=f"{goal} 的测试方案已验证通过。",
                    memory_type="validated_success",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="experiment_verified",
                    scope="private",
                    tags=tags,
                )
            )

        return records, failures, successes

    def _handle_user_feedback(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        payload = event.payload
        content = payload.get("content", "")
        problems = payload.get("problems") or []
        sentiment = payload.get("sentiment", "neutral")
        source_type = payload.get("source_type", "feedback")
        participant_id = payload.get("participant_id", "")

        records: list[LearningRecord] = []
        failures: list[FailureKnowledge] = []
        successes: list[SuccessKnowledge] = []

        source = f"user_feedback:{event.artifact_id or source_type}:{participant_id}"

        if sentiment == "negative" and (content or problems):
            memory_text = f"用户反馈负面：{content}"
            if problems:
                memory_text += f"。问题：{'；'.join(problems)}"
            records.append(
                LearningRecord(
                    memory=memory_text,
                    memory_type="user_preference",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="user_provided",
                    scope="user",
                    tags=["user_feedback", "negative"],
                )
            )
            if problems:
                for problem in problems:
                    failures.append(
                        FailureKnowledge(
                            problem=problem,
                            cause="用户反馈指出",
                            solution="待进一步验证",
                            affected_scope="用户体验",
                            verification="通过后续用户反馈验证",
                            source_project_id=event.project_id,
                            confidence="medium",
                            verification_status="user_provided",
                        )
                    )
        elif sentiment == "positive" and content:
            records.append(
                LearningRecord(
                    memory=f"用户反馈正面：{content}",
                    memory_type="validated_success",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="user_provided",
                    scope="user",
                    tags=["user_feedback", "positive"],
                )
            )
            successes.append(
                SuccessKnowledge(
                    goal="满足用户期望",
                    solution=content,
                    conditions=[source_type],
                    result="用户反馈正面",
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="user_provided",
                )
            )
        else:
            records.append(
                LearningRecord(
                    memory=f"用户反馈：{content}",
                    memory_type="user_preference",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="low",
                    verification_status="unverified",
                    scope="private",
                    tags=["user_feedback", sentiment],
                )
            )

        return records, failures, successes

    def _handle_validation_report(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        payload = event.payload
        conclusion = payload.get("conclusion", "")
        original_problem = payload.get("original_problem", "")
        tested_solution = payload.get("tested_solution", "")
        success_metrics = payload.get("success_metrics", "")

        records: list[LearningRecord] = []
        failures: list[FailureKnowledge] = []
        successes: list[SuccessKnowledge] = []

        source = f"validation_report:{event.artifact_id}"

        if conclusion == "pass":
            successes.append(
                SuccessKnowledge(
                    goal=original_problem,
                    solution=tested_solution,
                    conditions=[success_metrics] if success_metrics else [],
                    result="验证通过",
                    source_project_id=event.project_id,
                    confidence="high",
                    verification_status="experiment_verified",
                )
            )
            records.append(
                LearningRecord(
                    memory=f"方案 '{tested_solution}' 成功解决 '{original_problem}'，指标：{success_metrics}",
                    memory_type="validated_success",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="high",
                    verification_status="experiment_verified",
                    scope="user",
                    tags=["validation", "pass"],
                )
            )
        elif conclusion in ("fail", "partial"):
            failures.append(
                FailureKnowledge(
                    problem=original_problem,
                    cause=f"方案 '{tested_solution}' 未能完全解决问题",
                    solution="参考 Iteration Plan 进行优化",
                    affected_scope=tested_solution or "产品方案",
                    verification=success_metrics or "重新验证是否解决原始问题",
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="experiment_verified",
                )
            )
            records.append(
                LearningRecord(
                    memory=f"方案 '{tested_solution}' 对 '{original_problem}' 的效果为 {conclusion}",
                    memory_type="validated_failure" if conclusion == "fail" else "product_decision",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="medium",
                    verification_status="experiment_verified",
                    scope="private",
                    tags=["validation", conclusion],
                )
            )
        else:
            records.append(
                LearningRecord(
                    memory=f"方案 '{tested_solution}' 对 '{original_problem}' 的证据不足",
                    memory_type="project_fact",
                    source=source,
                    source_project_id=event.project_id,
                    confidence="low",
                    verification_status="unverified",
                    scope="private",
                    tags=["validation", "insufficient_evidence"],
                )
            )

        return records, failures, successes

    def _handle_iteration_plan(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        payload = event.payload
        items = payload.get("items", [])
        records: list[LearningRecord] = []
        failures: list[FailureKnowledge] = []
        successes: list[SuccessKnowledge] = []

        source = f"iteration_plan:{event.artifact_id}"

        for item in items:
            category = item.get("category", "")
            target = item.get("target", "")
            reason = item.get("reason", "")

            if category == "keep":
                successes.append(
                    SuccessKnowledge(
                        goal=f"保留 {target}",
                        solution=reason,
                        conditions=[],
                        result="迭代计划建议保留",
                        source_project_id=event.project_id,
                        confidence="medium",
                        verification_status="user_provided",
                    )
                )
                records.append(
                    LearningRecord(
                        memory=f"迭代计划中建议保留 {target}，理由：{reason}",
                        memory_type="validated_success",
                        source=source,
                        source_project_id=event.project_id,
                        confidence="medium",
                        verification_status="user_provided",
                        scope="private",
                        tags=["iteration", "keep"],
                    )
                )
            elif category in ("modify", "remove"):
                records.append(
                    LearningRecord(
                        memory=f"迭代计划建议 {category} {target}，理由：{reason}",
                        memory_type="product_decision",
                        source=source,
                        source_project_id=event.project_id,
                        confidence="medium",
                        verification_status="user_provided",
                        scope="private",
                        tags=["iteration", category],
                    )
                )
            elif category == "investigate":
                records.append(
                    LearningRecord(
                        memory=f"迭代计划建议调查 {target}，理由：{reason}",
                        memory_type="project_fact",
                        source=source,
                        source_project_id=event.project_id,
                        confidence="low",
                        verification_status="unverified",
                        scope="private",
                        tags=["iteration", "investigate"],
                    )
                )

        return records, failures, successes

    def _handle_decision(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        payload = event.payload
        decision = payload.get("decision", "")
        reason = payload.get("reason", "")
        alternatives = payload.get("alternatives", [])
        rejected = payload.get("rejected_reasons", {})

        records: list[LearningRecord] = []

        memory_text = f"决策：{decision}。理由：{reason}"
        if alternatives:
            memory_text += f"。备选方案：{', '.join(alternatives)}"
        if rejected:
            memory_text += f"。被拒绝方案及原因：{rejected}"

        records.append(
            LearningRecord(
                memory=memory_text,
                memory_type="product_decision",
                source=f"decision:{event.artifact_id}",
                source_project_id=event.project_id,
                confidence="medium",
                verification_status="user_provided",
                scope="private",
                tags=["decision"],
            )
        )
        return records, [], []

    def _handle_hardware_debug(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        payload = event.payload
        symptom = payload.get("symptom", "")
        root_cause = payload.get("root_cause", "")
        fix = payload.get("fix", "")
        affected_scope = payload.get("affected_scope", "")

        records: list[LearningRecord] = []
        failures: list[FailureKnowledge] = []

        if root_cause and fix:
            failure = FailureKnowledge(
                problem=symptom,
                cause=root_cause,
                solution=fix,
                affected_scope=affected_scope or "hardware",
                verification="重新测试硬件功能",
                source_project_id=event.project_id,
                confidence="high",
                verification_status="experiment_verified",
            )
            failures.append(failure)
            records.append(
                LearningRecord(
                    memory=f"硬件调试：{symptom} 的根本原因是 {root_cause}，解决方案：{fix}",
                    memory_type="validated_failure",
                    source=f"hardware_debug:{event.artifact_id}",
                    source_project_id=event.project_id,
                    confidence="high",
                    verification_status="experiment_verified",
                    scope="user",
                    tags=["hardware", "debug"],
                )
            )
        else:
            records.append(
                LearningRecord(
                    memory=f"硬件调试记录：{symptom}，原因待确认",
                    memory_type="project_fact",
                    source=f"hardware_debug:{event.artifact_id}",
                    source_project_id=event.project_id,
                    confidence="low",
                    verification_status="unverified",
                    scope="private",
                    tags=["hardware", "debug"],
                )
            )

        return records, failures, []

    def _handle_unknown(
        self, event: LearningEvent
    ) -> tuple[list[LearningRecord], list[FailureKnowledge], list[SuccessKnowledge]]:
        return [], [], []
