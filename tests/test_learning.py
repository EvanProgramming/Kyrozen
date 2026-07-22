"""Tests for Kyrozen Phase 9 Learning and Proactive Improvement System.

Covers three required cases:
1. Failure learning: extract and save failure knowledge from an ESP32 sensor event.
2. Success reuse: a validated success from project A is recommended to project B.
3. Wrong memory deletion: a learning record can be deleted and will no longer be used.
"""

from __future__ import annotations

import json

import pytest

from kyrozen.learning.extractor import LearningExtractor
from kyrozen.learning.models import (
    FailureKnowledge,
    LearningEvent,
    LearningRecord,
    SuccessKnowledge,
)
from kyrozen.learning.repository import LearningRepository
from kyrozen.learning.suggestions import SuggestionGenerator
from kyrozen.project import ProjectManager
from kyrozen.tools.learning_tools import (
    DeleteLearningRecordTool,
    SaveFailureKnowledgeTool,
    SaveLearningRecordTool,
    SaveSuccessKnowledgeTool,
)


# ---------------------------------------------------------------------------
# Case 1: Failure learning
# ---------------------------------------------------------------------------

def test_extract_failure_from_test_result():
    event = LearningEvent(
        event_type="test_result",
        project_id="proj_esp32",
        payload={
            "result": "failed",
            "test_case_name": "sensor_i2c_communication",
            "related_requirement": "传感器必须稳定读取数据",
            "related_feature": "I2C 传感器读取",
            "errors": "GPIO 冲突导致 I2C 时钟线被拉低",
            "environment": "ESP32-S3 + MPU6050",
        },
    )

    extractor = LearningExtractor()
    records, failures, successes = extractor.extract(event)

    assert len(failures) == 1
    failure = failures[0]
    assert "传感器通信错误" in failure.problem or "测试失败" in failure.problem
    assert "GPIO" in failure.cause
    assert failure.source_project_id == "proj_esp32"
    assert failure.confidence in ("low", "medium", "high")
    assert failure.verification_status in (
        "unverified",
        "user_provided",
        "externally_verified",
        "experiment_verified",
        "repeatedly_verified",
    )

    assert len(records) == 1
    record = records[0]
    assert record.memory_type == "validated_failure"
    assert record.scope == "private"
    assert record.source_project_id == "proj_esp32"


def test_save_failure_and_recommend_across_projects(
    project_manager: ProjectManager, learning_repository: LearningRepository
):
    project_a = project_manager.create(
        name="ESP32 Device A",
        description="ESP32-S3 传感器设备",
        goal="读取 I2C 传感器数据",
    )
    project_b = project_manager.create(
        name="ESP32 Device B",
        description="ESP32-S3 与 MPU6050 传感器设备",
        goal="读取 I2C 传感器数据",
    )

    failure = FailureKnowledge(
        problem="ESP32-S3 与 MPU6050 传感器设备通信失败",
        cause="GPIO 冲突导致 I2C 时钟线被拉低",
        solution="更换 I2C 引脚为 IO8/IO9",
        affected_scope="ESP32-S3 + MPU6050 传感器设备",
        verification="重新运行 sensor_i2c_communication 测试应通过",
        source_project_id=project_a.id,
        confidence="high",
        verification_status="experiment_verified",
    )

    tool = SaveFailureKnowledgeTool(project_manager, learning_repository)
    result = tool.execute("save", {"failure": failure.to_dict()})
    assert result.success is True
    assert result.data is not None

    generator = SuggestionGenerator(project_manager, learning_repository)
    suggestions = generator.analyze(project_b.id)

    cross_project = [s for s in suggestions if s.category == "new_opportunity"]
    assert len(cross_project) >= 1
    assert any("MPU6050" in s.suggestion or "GPIO" in s.suggestion for s in cross_project)


# ---------------------------------------------------------------------------
# Case 2: Success reuse
# ---------------------------------------------------------------------------

def test_success_reuse_across_projects(
    project_manager: ProjectManager, learning_repository: LearningRepository
):
    project_a = project_manager.create(
        name="Project A",
        description="分层架构的 Web 服务",
        goal="构建可扩展的后端服务",
    )
    project_b = project_manager.create(
        name="Project B",
        description="构建可扩展的后端服务",
        goal="构建可扩展的后端服务",
    )

    success = SuccessKnowledge(
        goal="构建可扩展的后端服务",
        solution="使用分层架构：controller/service/repository",
        conditions=["Python + FastAPI", "SQLAlchemy ORM"],
        result="项目 A 中稳定运行并支持水平扩展",
        source_project_id=project_a.id,
        confidence="high",
        verification_status="repeatedly_verified",
    )

    tool = SaveSuccessKnowledgeTool(project_manager, learning_repository)
    result = tool.execute("save", {"success": success.to_dict()})
    assert result.success is True

    record = LearningRecord(
        memory="分层架构 controller/service/repository 在 Python Web 服务中验证成功",
        memory_type="validated_success",
        source="validation_report:proj_a_final",
        source_project_id=project_a.id,
        confidence="high",
        verification_status="repeatedly_verified",
        scope="user",
        tags=["architecture", "fastapi", "python"],
    )
    record_tool = SaveLearningRecordTool(project_manager, learning_repository)
    record_result = record_tool.execute("save", {"record": record.to_dict()})
    assert record_result.success is True

    generator = SuggestionGenerator(project_manager, learning_repository)
    suggestions = generator.analyze(project_b.id)

    cross_project = [s for s in suggestions if s.category == "new_opportunity"]
    assert len(cross_project) >= 1
    assert any(
        "分层架构" in s.suggestion or "controller/service/repository" in s.suggestion
        for s in cross_project
    )


# ---------------------------------------------------------------------------
# Case 3: Wrong memory deletion
# ---------------------------------------------------------------------------

def test_delete_wrong_learning_record(
    project_manager: ProjectManager, learning_repository: LearningRepository
):
    project = project_manager.create(
        name="Wrong Memory Project",
        description="用于测试错误记忆删除",
        goal="验证删除后不再使用",
    )

    record = LearningRecord(
        memory="用户偏好深色主题",
        memory_type="user_preference",
        source="user_chat",
        source_project_id=project.id,
        confidence="low",
        verification_status="unverified",
        scope="private",
    )

    tool = SaveLearningRecordTool(project_manager, learning_repository)
    save_result = tool.execute("save", {"record": record.to_dict()})
    assert save_result.success is True
    record_id = save_result.data["record_id"]

    # Verify the record exists.
    records_before = learning_repository.list_records()
    assert any(r.id == record_id for r in records_before)

    delete_tool = DeleteLearningRecordTool(project_manager, learning_repository)
    delete_result = delete_tool.execute("delete", {"record_id": record_id})
    assert delete_result.success is True

    # Verify the record no longer exists.
    records_after = learning_repository.list_records()
    assert not any(r.id == record_id for r in records_after)

    # Re-deleting the same record should fail.
    second_delete = delete_tool.execute("delete", {"record_id": record_id})
    assert second_delete.success is False


# ---------------------------------------------------------------------------
# Validation and privacy
# ---------------------------------------------------------------------------

def test_learning_record_validates_enum_fields():
    with pytest.raises(ValueError):
        LearningRecord(memory="x", memory_type="invalid_type")

    with pytest.raises(ValueError):
        LearningRecord(memory="x", memory_type="user_preference", confidence="invalid")

    with pytest.raises(ValueError):
        LearningRecord(
            memory="x",
            memory_type="user_preference",
            verification_status="invalid",
        )

    with pytest.raises(ValueError):
        LearningRecord(memory="x", memory_type="user_preference", scope="invalid")


def test_private_learning_record_not_reused_across_projects(
    project_manager: ProjectManager, learning_repository: LearningRepository
):
    project_a = project_manager.create(
        name="Private A", description="私有记忆项目 A", goal="目标 A"
    )
    project_b = project_manager.create(
        name="Private B", description="私有记忆项目 B", goal="目标 A"
    )

    record = LearningRecord(
        memory="项目 A 的私有事实",
        memory_type="project_fact",
        source="agent",
        source_project_id=project_a.id,
        confidence="medium",
        verification_status="user_provided",
        scope="private",
    )
    tool = SaveLearningRecordTool(project_manager, learning_repository)
    tool.execute("save", {"record": record.to_dict()})

    generator = SuggestionGenerator(project_manager, learning_repository)
    suggestions = generator.analyze(project_b.id)

    cross_project = [s for s in suggestions if s.category == "new_opportunity"]
    assert not any("项目 A 的私有事实" in s.suggestion for s in cross_project)
