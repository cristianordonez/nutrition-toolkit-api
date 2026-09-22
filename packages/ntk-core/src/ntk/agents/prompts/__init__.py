"""Prompt text shared across apps.

The NCP prompt lives here rather than in either app because both generate
notes from it: cloud-api serves generation over HTTP, and the desktop engine
generates on-device. Two copies of a prompt this long would drift.
"""

from __future__ import annotations

import functools
import pathlib

_PROMPT_DIR = pathlib.Path(__file__).parent


@functools.cache
def ncp_instructions() -> str:
    """Return the Nutrition Care Process note instructions."""
    return (_PROMPT_DIR / "ncp_prompt.md").read_text(encoding="utf-8")


__all__ = ["ncp_instructions"]
