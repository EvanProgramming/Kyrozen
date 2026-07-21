"""Tests for JsonFileMemory and ProjectMemory."""

from __future__ import annotations

import os

from kyrozen.memory import JsonFileMemory, ProjectMemory


def test_json_file_memory_save_and_query(temp_dir: str):
    path = os.path.join(temp_dir, "memory.json")
    mem = JsonFileMemory(path)
    record = mem.save("project", "用户已购买ESP32-S3", project_id="proj_a")
    assert record.id.startswith("mem_")
    assert record.category == "project"

    results = mem.query(category="project", project_id="proj_a")
    assert len(results) == 1
    assert results[0].content == "用户已购买ESP32-S3"


def test_json_file_memory_persists(temp_dir: str):
    path = os.path.join(temp_dir, "memory.json")
    mem1 = JsonFileMemory(path)
    mem1.save("project", "预算100美元", project_id="proj_b")

    mem2 = JsonFileMemory(path)
    results = mem2.query(category="project", project_id="proj_b")
    assert len(results) == 1
    assert results[0].content == "预算100美元"


def test_json_file_memory_filters_by_project_id(temp_dir: str):
    path = os.path.join(temp_dir, "memory.json")
    mem = JsonFileMemory(path)
    mem.save("project", "A", project_id="proj_1")
    mem.save("project", "B", project_id="proj_2")

    assert len(mem.query(project_id="proj_1")) == 1
    assert mem.query(project_id="proj_1")[0].content == "A"


def test_json_file_memory_update_and_delete(temp_dir: str):
    path = os.path.join(temp_dir, "memory.json")
    mem = JsonFileMemory(path)
    r = mem.save("note", "old", project_id="proj_c")
    updated = mem.update(r.id, "new", project_id="proj_c")
    assert updated is not None
    assert updated.content == "new"

    assert mem.delete(r.id) is True
    assert len(mem.query(project_id="proj_c")) == 0


def test_project_memory_auto_scopes(temp_dir: str):
    path = os.path.join(temp_dir, "memory.json")
    backend = JsonFileMemory(path)
    pm1 = ProjectMemory("proj_x", backend)
    pm2 = ProjectMemory("proj_y", backend)

    pm1.save("project", "X memory")
    pm2.save("project", "Y memory")

    assert len(pm1.query()) == 1
    assert pm1.query()[0].content == "X memory"
    assert len(pm2.query()) == 1
    assert pm2.query()[0].content == "Y memory"
