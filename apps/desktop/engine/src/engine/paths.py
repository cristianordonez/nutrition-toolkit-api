"""Where the app keeps its data, logs, and configuration on this machine.

Uses the platform's own conventions rather than a dotfile in ``$HOME``, so on
macOS the database lands in ``~/Library/Application Support`` and logs in
``~/Library/Logs``, where a user would look for them and where backup tools
expect them.
"""

from __future__ import annotations

import logging
import pathlib

import platformdirs

APP_NAME = "NutritionToolkit"


logger = logging.getLogger(__name__)


def data_dir() -> pathlib.Path:
    """Return the directory holding the local database."""
    return pathlib.Path(platformdirs.user_data_dir(APP_NAME))


def log_dir() -> pathlib.Path:
    """Return the directory holding log files."""
    return pathlib.Path(platformdirs.user_log_dir(APP_NAME))


def config_dir() -> pathlib.Path:
    """Return the directory holding configuration files."""
    return pathlib.Path(platformdirs.user_config_dir(APP_NAME))


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    """Create ``path`` if it is missing and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "APP_NAME",
    "config_dir",
    "data_dir",
    "ensure_dir",
    "log_dir",
]
