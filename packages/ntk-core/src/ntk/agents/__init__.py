"""Prompts and agent assets shared by cloud-api and the desktop engine."""

from __future__ import annotations

from .calculator_tools import CALCULATOR_TOOLSET, CalculatorToolDependencies
from .prompts import ncp_instructions

__all__ = [
    "CALCULATOR_TOOLSET",
    "CalculatorToolDependencies",
    "ncp_instructions",
]
