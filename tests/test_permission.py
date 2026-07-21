"""Tests for the permission system."""

from __future__ import annotations

from kyrozen.core.permission import PermissionManager


def test_strict_mode_blocks_high_risk():
    pm = PermissionManager(mode="strict")
    decision = pm.check("file_write", "write", {"path": "test.txt"})
    assert not decision.allowed
    assert decision.requires_confirmation
    assert "requires user confirmation" in decision.reason


def test_strict_mode_allows_low_risk():
    pm = PermissionManager(mode="strict")
    decision = pm.check("file_read", "read", {"path": "test.txt"})
    assert decision.allowed
    assert not decision.requires_confirmation


def test_permissive_mode_allows_all():
    pm = PermissionManager(mode="permissive")
    decision = pm.check("terminal", "execute", {"command": "rm -rf /"})
    assert decision.allowed
    assert not decision.requires_confirmation


def test_confirm_returns_allowed():
    pm = PermissionManager(mode="strict")
    decision = pm.confirm("file_write", "write", {})
    assert decision.allowed
    assert not decision.requires_confirmation
