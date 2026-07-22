"""Tools for Kyrozen Phase 9 Learning and Proactive Improvement."""

from __future__ import annotations

import json
from typing import Any

from kyrozen.learning.models import (
    VALID_SUGGESTION_STATUSES,
    FailureKnowledge,
    LearningEvent,
    LearningRecord,
    Suggestion,
    SuccessKnowledge,
)
from kyrozen.learning.repository import LearningRepository
from kyrozen.tools.base import Tool, ToolParameter, ToolResult, ToolSchema

if True:  # typing-only guard for circular imports
    from kyrozen.project.manager import ProjectManager


class _LearningTool(Tool):
    """Base class for Phase 9 learning tools."""

    def __init__(
        self,
        project_manager: "ProjectManager | None" = None,
        repository: LearningRepository | None = None,
    ) -> None:
        self.project_manager = project_manager
        self.repository = repository

    def _check_repository(self) -> ToolResult | None:
        if self.repository is None:
            return ToolResult(success=False, data=None, error="Learning repository not available")
        return None

    def _check_project(self, project_id: str) -> ToolResult | None:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        if self.project_manager.get(project_id) is None:
            return ToolResult(success=False, data=None, error=f"Project '{project_id}' not found")
        return None


class SaveLearningRecordTool(_LearningTool):
    """Save a generic learning record to the database."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "save_learning_record"
        self.description = "Save a learning record (preference, capability, fact, decision, success, failure, external knowledge)."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="record", param_type="object", description="LearningRecord fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        err = self._check_repository()
        if err:
            return err
        record_data = parameters.get("record", {})
        try:
            record = LearningRecord.from_dict(record_data)
            self.repository.save_record(record)
            return ToolResult(success=True, data={"record_id": record.id})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveFailureKnowledgeTool(_LearningTool):
    """Save a validated failure pattern to the database."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "save_failure_knowledge"
        self.description = "Save a failure knowledge entry (problem, cause, solution, affected scope)."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="failure", param_type="object", description="FailureKnowledge fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        err = self._check_repository()
        if err:
            return err
        failure_data = parameters.get("failure", {})
        try:
            failure = FailureKnowledge.from_dict(failure_data)
            self.repository.save_failure(failure)
            return ToolResult(success=True, data={"failure_id": failure.id})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveSuccessKnowledgeTool(_LearningTool):
    """Save a validated success pattern to the database."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "save_success_knowledge"
        self.description = "Save a success knowledge entry (goal, solution, conditions, result)."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="success", param_type="object", description="SuccessKnowledge fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        err = self._check_repository()
        if err:
            return err
        success_data = parameters.get("success", {})
        try:
            success = SuccessKnowledge.from_dict(success_data)
            self.repository.save_success(success)
            return ToolResult(success=True, data={"success_id": success.id})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class DeleteLearningRecordTool(_LearningTool):
    """Delete a learning record from the database by its record id."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "delete_learning_record"
        self.description = "Delete a learning record from the database by record_id."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "delete": [
                    ToolParameter(name="record_id", param_type="string", description="Learning record id to delete"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        err = self._check_repository()
        if err:
            return err
        record_id = parameters.get("record_id")
        if not record_id:
            return ToolResult(success=False, data=None, error="Missing record_id")
        deleted = (
            self.repository.delete_record(record_id)
            or self.repository.delete_failure(record_id)
            or self.repository.delete_success(record_id)
        )
        if not deleted:
            return ToolResult(success=False, data=None, error=f"Learning record '{record_id}' not found")
        return ToolResult(success=True, data={"deleted": True})


class SaveSuggestionTool(_LearningTool):
    """Save a proactive improvement suggestion to the database."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "save_suggestion"
        self.description = "Save a proactive improvement suggestion for a project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="suggestion", param_type="object", description="Suggestion fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        err = self._check_repository()
        if err:
            return err
        suggestion_data = parameters.get("suggestion", {})
        try:
            suggestion = Suggestion.from_dict(suggestion_data)
            project_err = self._check_project(suggestion.source_project_id)
            if project_err:
                return project_err
            self.repository.save_suggestion(suggestion)
            return ToolResult(success=True, data={"suggestion_id": suggestion.id})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class UpdateSuggestionStatusTool(_LearningTool):
    """Update the status of a suggestion (accepted, rejected, later, ignored)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "update_suggestion_status"
        self.description = "Update the status of a suggestion by suggestion_id."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "update": [
                    ToolParameter(name="suggestion_id", param_type="string", description="Suggestion record id"),
                    ToolParameter(name="status", param_type="string", description="new status: accepted | rejected | later | ignored"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        err = self._check_repository()
        if err:
            return err
        suggestion_id = parameters.get("suggestion_id")
        status = parameters.get("status")
        if not suggestion_id:
            return ToolResult(success=False, data=None, error="Missing suggestion_id")
        if status not in VALID_SUGGESTION_STATUSES:
            return ToolResult(success=False, data=None, error=f"Invalid status '{status}'")
        updated = self.repository.update_suggestion_status(suggestion_id, status)
        if not updated:
            return ToolResult(success=False, data=None, error=f"Suggestion '{suggestion_id}' not found")
        return ToolResult(success=True, data={"suggestion_id": suggestion_id, "status": status})


class ExtractLearningFromEventTool(_LearningTool):
    """Extract learning records from a project event (test_result, feedback, etc.)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "extract_learning_from_event"
        self.description = "Analyze a project event and return proposed learning records without saving them."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "extract": [
                    ToolParameter(name="event", param_type="object", description="LearningEvent fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        from kyrozen.learning.extractor import LearningExtractor

        event_data = parameters.get("event", {})
        try:
            event = LearningEvent.from_dict(event_data)
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))

        extractor = LearningExtractor()
        records, failures, successes = extractor.extract(event)
        return ToolResult(
            success=True,
            data={
                "records": [r.to_dict() for r in records],
                "failures": [f.to_dict() for f in failures],
                "successes": [s.to_dict() for s in successes],
            },
        )


class RunProjectAnalysisTool(_LearningTool):
    """Run proactive analysis on a project and return improvement suggestions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.name = "run_project_analysis"
        self.description = "Analyze a project's artifacts and generate proactive improvement suggestions."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "analyze": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID to analyze"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        from kyrozen.learning.suggestions import SuggestionGenerator

        project_id = parameters.get("project_id")
        project_err = self._check_project(project_id)
        if project_err:
            return project_err

        generator = SuggestionGenerator(self.project_manager, self.repository)
        suggestions = generator.analyze(project_id)
        return ToolResult(
            success=True,
            data={"suggestions": [s.to_dict() for s in suggestions]},
        )
