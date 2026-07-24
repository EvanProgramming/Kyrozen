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


def test_session_trust_mode_blocks_first_time():
    pm = PermissionManager(mode="session_trust")
    decision = pm.check("file_write", "write", {"path": "test.txt"})
    assert not decision.allowed
    assert decision.requires_confirmation


def test_session_trust_allows_after_trust_for_session():
    pm = PermissionManager(mode="session_trust")
    pm.trust_for_session("file_write", "write")
    decision = pm.check("file_write", "write", {"path": "test.txt"})
    assert decision.allowed
    assert not decision.requires_confirmation
    assert "Session-trusted" in decision.reason


def test_session_trust_does_not_bleed_to_other_actions():
    pm = PermissionManager(mode="session_trust")
    pm.trust_for_session("file_write", "write")
    decision = pm.check("terminal", "execute", {"command": "ls"})
    assert not decision.allowed
    assert decision.requires_confirmation


def test_full_trust_mode_allows_all():
    pm = PermissionManager(mode="full_trust")
    decision = pm.check("terminal", "execute", {"command": "rm -rf /"})
    assert decision.allowed
    assert not decision.requires_confirmation
    assert "full trust" in decision.reason


def test_reset_session_trust_clears_grants():
    pm = PermissionManager(mode="session_trust")
    pm.trust_for_session("file_write", "write")
    assert pm.is_session_trusted("file_write", "write")
    pm.reset_session_trust()
    assert not pm.is_session_trusted("file_write", "write")
    decision = pm.check("file_write", "write", {})
    assert not decision.allowed
