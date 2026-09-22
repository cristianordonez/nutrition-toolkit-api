"""Where the app keeps its data, logs, and configuration on this machine.

Uses the platform's own conventions rather than a dotfile in ``$HOME``, so on
macOS the database lands in ``~/Library/Application Support`` and logs in
``~/Library/Logs``, where a user would look for them and where backup tools
expect them.

Earlier versions kept everything in ``~/.nutrition-toolkit``. That directory is
migrated on first use rather than abandoned, because it holds the resident
records someone has already ingested.
"""

from __future__ import annotations

import logging
import pathlib

import platformdirs

APP_NAME = "NutritionToolkit"

#: Pre-platformdirs location, kept only so existing installs can be moved.
LEGACY_DIR = pathlib.Path("~/.nutrition-toolkit").expanduser()

logger = logging.getLogger(__name__)


def data_dir() -> pathlib.Path:
    """Return the directory holding the local databases."""
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


def migrate_legacy_data() -> list[str]:
    """Move any pre-platformdirs files into the data directory.

    Only moves a file when nothing occupies its destination, so a real
    database is never overwritten by a stale one. Both locations live under
    ``$HOME`` on the same filesystem, which makes each move atomic.

    Returns the names of the files moved, for logging by the caller.
    """
    if not LEGACY_DIR.is_dir():
        return []

    destination = ensure_dir(data_dir())
    moved: list[str] = []
    for source in sorted(LEGACY_DIR.iterdir()):
        if not source.is_file():
            continue
        target = destination / source.name
        if target.exists():
            logger.warning(
                "Not migrating %s: %s already exists",
                source,
                target,
            )
            continue
        source.rename(target)
        moved.append(source.name)

    # Only tidy up once the directory has nothing left to lose.
    if not any(LEGACY_DIR.iterdir()):
        LEGACY_DIR.rmdir()
    return moved


__all__ = [
    "APP_NAME",
    "LEGACY_DIR",
    "config_dir",
    "data_dir",
    "ensure_dir",
    "log_dir",
    "migrate_legacy_data",
]
