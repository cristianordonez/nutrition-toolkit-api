from __future__ import annotations

import logging
import typing
from logging.handlers import TimedRotatingFileHandler

if typing.TYPE_CHECKING:
    from pathlib import Path

_MINIMUM_LIBRARY_LOG_LEVELS = {
    # Optional module configs legitimately return 404 for some Hugging Face models.
    "sentence_transformers.util.file_io": logging.INFO,
}


def setup_logging(
    log_file: Path | None = None,
    interval: int | None = None,
    backup_count: int | None = None,
    *,
    debug: bool = False,
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
    logger.setLevel(level)
    for logger_name, minimum_level in _MINIMUM_LIBRARY_LOG_LEVELS.items():
        logging.getLogger(logger_name).setLevel(minimum_level)
    return logger


def _setup_stdout_handler(level: typing.Literal[10, 20]) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(fmt=_get_formatter())
    return handler


def _setup_file_handler(
    log_file: Path,
    interval: int | None,
    backup_count: int | None,
) -> TimedRotatingFileHandler:
    interval = 1 if interval is None else interval
    backup_count = 30 if backup_count is None else backup_count
    if log_file.exists() is False:
        msg = f"Log file not found: {log_file}"
        raise FileNotFoundError(msg)
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
    return logging.Formatter(
        fmt="%(levelname)s | %(asctime)s | %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
