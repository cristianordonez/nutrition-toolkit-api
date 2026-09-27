"""Prompt text used by the on-device agents."""

from __future__ import annotations

import functools
import pathlib

_PROMPT_DIR = pathlib.Path(__file__).parent


@functools.cache
def ncp_instructions() -> str:
    """Return the Nutrition Care Process note instructions."""
    return (_PROMPT_DIR / "ncp_prompt.md").read_text(encoding="utf-8")


@functools.cache
def data_extraction_instructions() -> str:
    """Return the clinical-fact extraction instructions."""
    return (_PROMPT_DIR / "data_extraction_prompt.md").read_text(encoding="utf-8")


__all__ = ["data_extraction_instructions", "ncp_instructions"]
