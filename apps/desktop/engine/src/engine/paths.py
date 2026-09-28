"""Where the app keeps its data, logs, and configuration on this machine.

Uses the platform's own conventions rather than a dotfile in ``$HOME``, so on
macOS the database lands in ``~/Library/Application Support`` and logs in
``~/Library/Logs``, where a user would look for them and where backup tools
expect them.
"""

from __future__ import annotations

import json
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


def bundled_embedding_model_dir() -> pathlib.Path:
    """Resolve the read-only MiniLM assets beside the installed engine package.

    The same layout is used by an editable checkout, a wheel, and PyInstaller's
    bundled package data. Never consult the working directory or HF cache.
    """
    assets = pathlib.Path(__file__).resolve().parent / "assets" / "models"
    manifest_path = assets / "minilm.json"
    if not manifest_path.is_file():
        msg = (
            f"Bundled MiniLM manifest is missing: {manifest_path}. "
            "Reinstall the engine."
        )
        raise FileNotFoundError(msg)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    directory = assets / manifest["directory"]
    for filename in manifest["files"]:
        asset = directory / filename
        if not asset.is_file() or asset.stat().st_size == 0:
            msg = (
                f"Bundled MiniLM model file is missing or empty: {asset}. "
                "Reinstall the engine; in a source checkout, run "
                "apps/desktop/engine/scripts/prepare_embedding_model.py first. "
                "Runtime downloads are disabled."
            )
            raise FileNotFoundError(msg)
    return directory


def bundled_reference_database() -> pathlib.Path | None:
    """Return the shipped starter database, if this build includes one.

    It holds reference data only -- the knowledge base, NCP style examples and
    their vectors -- and is copied into place when the user has no database
    yet. A source checkout without it simply starts from an empty database.
    """
    path = (
        pathlib.Path(__file__).resolve().parent / "assets" / "reference" / ("facts.db")
    )
    return path if path.is_file() else None


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    """Create ``path`` if it is missing and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "APP_NAME",
    "bundled_embedding_model_dir",
    "bundled_reference_database",
    "config_dir",
    "data_dir",
    "ensure_dir",
    "log_dir",
]
