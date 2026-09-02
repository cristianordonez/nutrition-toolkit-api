from __future__ import annotations

import logging
import typing

import pytest

from ntk.logger import (
    _get_formatter,
    _setup_file_handler,
    _setup_stdout_handler,
    setup_logging,
)

if typing.TYPE_CHECKING:
    from pathlib import Path

_BACKUP_COUNT = 5


def test_get_formatter_returns_formatter() -> None:
    formatter = _get_formatter()
    assert isinstance(formatter, logging.Formatter)
    assert (
        vars(formatter)["_fmt"] == "%(levelname)s | %(asctime)s | %(name)s: %(message)s"
    )
    assert formatter.datefmt == "%Y-%m-%d %H:%M:%S"


def test_setup_stdout_handler_sets_level_and_formatter() -> None:
    handler = _setup_stdout_handler(logging.INFO)

    assert isinstance(handler, logging.StreamHandler)
    assert handler.level == logging.INFO
    assert isinstance(handler.formatter, logging.Formatter)


def test_setup_file_handler_raises_when_file_missing(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.log"

    with pytest.raises(FileNotFoundError, match="Log file not found"):
        _setup_file_handler(missing_file, interval=1, backup_count=2)


def test_setup_file_handler_creates_timed_rotating_handler(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_text("")

    handler = _setup_file_handler(log_file, interval=2, backup_count=5)

    assert handler.baseFilename == str(log_file)
    assert handler.backupCount == _BACKUP_COUNT
    assert handler.when.lower() == "midnight"
    assert isinstance(handler.formatter, logging.Formatter)


def test_setup_logging_adds_handlers(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    log_file.write_text("")

    logger = setup_logging(log_file=log_file, interval=1, backup_count=1)
    assert isinstance(logger, logging.Logger)
    assert any(
        isinstance(handler, logging.StreamHandler) for handler in logger.handlers
    )
    assert any(
        getattr(handler, "baseFilename", None) == str(log_file)
        for handler in logger.handlers
    )


def test_setup_logging_debug_sets_log_level() -> None:
    logger = setup_logging(debug=True)
    assert logger.level == logging.DEBUG
    assert logging.getLogger("sentence_transformers.util.file_io").level == logging.INFO
