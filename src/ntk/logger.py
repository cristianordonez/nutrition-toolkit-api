from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal


def setup_logging(
    debug: bool = False,
    log_file: Path | None = None,
    interval: int | None = None,
    backup_count: int | None = None,
) -> logging.Logger:
    """Set up root logger when app is initialized.

    :param debug: change log level to debug, defaults to False
    :param log_file: path to emit log file to, defaults to None
    :param interval: how often to rotate log files, defaults to 1
    :param backup_count: how many backup log files to keep, defaults to 30
    """
    logger = logging.getLogger()
    level = logging.DEBUG if debug else logging.INFO
    stdout_handler = _setup_stdout_handler(level)
    if log_file is not None:
        file_handler = _setup_file_handler(log_file, interval, backup_count)
        logger.addHandler(hdlr=file_handler)
    logger.addHandler(stdout_handler)
    logger.setLevel(debug)
    return logger


def _setup_stdout_handler(level: Literal[10, 20]) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(fmt=_get_formatter())
    return handler


def _setup_file_handler(
    log_file: Path, interval: int | None, backup_count: int | None
) -> TimedRotatingFileHandler:
    interval = 1 if interval is None else interval
    backup_count = 30 if backup_count is None else backup_count
    if log_file.exists() is False:
        raise FileNotFoundError(f"Log file not found: {log_file}")
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=interval,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(fmt=_get_formatter())
    return handler


def _get_formatter() -> logging.Formatter:
    formatter = logging.Formatter(
        fmt="%(levelname)s | %(asctime)s | %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return formatter
