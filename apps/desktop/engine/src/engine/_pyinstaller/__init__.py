"""Expose engine data hooks to PyInstaller without custom command-line flags."""

from __future__ import annotations

from pathlib import Path


def get_hook_dirs() -> list[str]:
    """Return the hook directory inside this installed package."""
    return [str(Path(__file__).resolve().parent)]
