"""Regression tests for KyrozenLogger stdlib-method parity.

The 2026-07-30 Round-4 acceptance found that callers (desktop agent, research
tools, server) sometimes use logger.debug(...)/logger.info(...)/logger.critical(...)
etc. KyrozenLogger must behave as a drop-in for logging.Logger so these calls
never raise AttributeError (which surfaced as the "task launch failed:
'KyrozenLogger' object has no attribute 'debug'" blocker).
"""

import logging

from kyrozen.logs.logger import KyrozenLogger, get_logger


def _tmp_logger(tmp_path):
    return KyrozenLogger(log_level="DEBUG", log_dir=str(tmp_path / "logs"))


def test_standard_methods_exist_and_do_not_raise(tmp_path):
    log = _tmp_logger(tmp_path)
    # These must not raise AttributeError.
    log.debug("debug %s", "x")
    log.info("info %s", "y")
    log.warning("warning %s", "z")  # already existed
    log.error("error %s", "e")      # already existed
    log.critical("critical %s", "c")
    log.exception("exception %s", "ex")
    # no exception => pass


def test_delegated_stdlib_attributes(tmp_path):
    log = _tmp_logger(tmp_path)
    # setLevel / isEnabledFor / getEffectiveLevel delegate to underlying logger.
    log.setLevel(logging.WARNING)
    assert log.isEnabledFor(logging.DEBUG) is False
    assert log.isEnabledFor(logging.WARNING) is True
    assert log.getEffectiveLevel() == logging.WARNING
    # hasHandlers is a stdlib attribute we didn't define -> delegated.
    assert isinstance(log.hasHandlers(), bool)


def test_get_logger_returns_drop_in(tmp_path, monkeypatch):
    monkeypatch.setenv("KYROZEN_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("KYROZEN_LOG_LEVEL", raising=False)
    lg = get_logger()
    assert isinstance(lg, KyrozenLogger)
    lg.info("via get_logger")
    lg.debug("via get_logger debug")
