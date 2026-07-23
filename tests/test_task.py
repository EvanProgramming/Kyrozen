"""Tests for task management."""

from __future__ import annotations

import os

import pytest

from kyrozen.core.task import Task, TaskManager


def test_task_lifecycle():
    task = Task(title="Analyze project", description="Analyze the project structure")
    assert task.status == "pending"
    task.update_status("running")
    assert task.status == "running"
    step = task.add_step("Call list_dir")
    assert step.status == "pending"
    step.status = "completed"
    task.complete(result={"answer": "Done"})
    assert task.status == "completed"
    assert task.result["answer"] == "Done"


def test_task_fail():
    task = Task(title="Fail task")
    task.fail("Something went wrong")
    assert task.status == "failed"
    assert "Something went wrong" in task.errors


def test_task_manager_persistence(temp_dir: str):
    store_path = os.path.join(temp_dir, "tasks.json")
    tm = TaskManager(store_path=store_path)
    task = tm.create(title="Test", description="Test task")
    task.update_status("running")
    tm.update(task)

    tm2 = TaskManager(store_path=store_path)
    loaded = tm2.get(task.id)
    assert loaded is not None
    assert loaded.title == "Test"
    assert loaded.status == "running"


def test_task_manager_list(temp_dir: str):
    tm = TaskManager(store_path=os.path.join(temp_dir, "tasks.json"))
    t1 = tm.create(title="Task 1")
    t2 = tm.create(title="Task 2")
    tasks = tm.list_tasks()
    assert len(tasks) == 2
    assert {t.id for t in tasks} == {t1.id, t2.id}


def test_task_status_transition_validation():
    task = Task(title="Transition test")
    task.update_status("running")
    with pytest.raises(ValueError):
        task.update_status("pending")
    task.update_status("completed")
    with pytest.raises(ValueError):
        task.update_status("running")


def test_task_force_status_transition():
    task = Task(title="Force transition")
    task.update_status("completed")
    task.update_status("running", force=True)
    assert task.status == "running"
