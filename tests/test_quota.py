"""Tests for the desktop client quota manager."""

from __future__ import annotations

import pytest

from kyrozen.desktop.quota import QuotaManager


def test_quota_unlimited_by_default():
    manager = QuotaManager(default_limit=0)
    status = manager.check_quota("user_1", estimated_tokens=1_000_000)
    assert status.allowed is True
    assert status.remaining == -1


def test_quota_enforces_limit():
    manager = QuotaManager(default_limit=100)
    status = manager.check_quota("user_1", estimated_tokens=50)
    assert status.allowed is True
    assert status.remaining == 100

    manager.record_usage("user_1", 60, 0)
    status = manager.check_quota("user_1", estimated_tokens=50)
    assert status.allowed is False
    assert status.remaining == 40


def test_quota_per_user_isolation():
    manager = QuotaManager(default_limit=100)
    manager.record_usage("user_a", 80, 0)
    manager.record_usage("user_b", 10, 0)

    assert manager.check_quota("user_a", estimated_tokens=30).allowed is False
    assert manager.check_quota("user_b", estimated_tokens=30).allowed is True


def test_quota_set_user_limit():
    manager = QuotaManager(default_limit=100)
    manager.set_user_limit("vip", 500)
    manager.record_usage("vip", 200, 0)
    assert manager.check_quota("vip", estimated_tokens=250).allowed is True
    assert manager.check_quota("vip", estimated_tokens=350).allowed is False


def test_quota_reset_usage():
    manager = QuotaManager(default_limit=100)
    manager.record_usage("user_1", 150, 0)
    assert manager.check_quota("user_1", estimated_tokens=1).allowed is False

    manager.reset_usage("user_1")
    assert manager.check_quota("user_1", estimated_tokens=1).allowed is True

    manager.record_usage("user_1", 50, 0)
    manager.record_usage("user_2", 50, 0)
    manager.reset_usage()
    assert manager.get_usage("user_1") == 0
    assert manager.get_usage("user_2") == 0
