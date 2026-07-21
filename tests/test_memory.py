"""Tests for the memory interface."""

from __future__ import annotations

from kyrozen.memory.interface import InMemoryMemory


def test_save_and_query():
    mem = InMemoryMemory()
    record = mem.save("user", "Hello Kyrozen", task_id="t1")
    assert record.category == "user"
    assert record.content == "Hello Kyrozen"
    results = mem.query(category="user", query="Kyrozen")
    assert len(results) == 1
    assert results[0].content == "Hello Kyrozen"


def test_update_and_delete():
    mem = InMemoryMemory()
    record = mem.save("project", "Initial note")
    updated = mem.update(record.id, "Updated note")
    assert updated is not None
    assert updated.content == "Updated note"
    assert mem.delete(record.id)
    assert not mem.delete("nonexistent")
    assert mem.query(query="Updated") == []


def test_query_limit():
    mem = InMemoryMemory()
    for i in range(5):
        mem.save("knowledge", f"Fact {i}")
    results = mem.query(category="knowledge", limit=3)
    assert len(results) == 3
