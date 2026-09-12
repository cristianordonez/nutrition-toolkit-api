"""Reusable tools for nutrition agents."""

from __future__ import annotations

from dataclasses import dataclass

from .calculator_tools import CALCULATOR_TOOLSET, CalculatorToolDependencies
from .knowledge_search_tools import (
    KNOWLEDGE_SEARCH_TOOLSET,
    KnowledgeSearchToolDependencies,
)


@dataclass(frozen=True)
class AssessmentToolDependencies(
    CalculatorToolDependencies,
    KnowledgeSearchToolDependencies,
):
    """Runtime dependencies shared by every assessment-agent toolset."""


__all__ = [
    "CALCULATOR_TOOLSET",
    "KNOWLEDGE_SEARCH_TOOLSET",
    "AssessmentToolDependencies",
    "CalculatorToolDependencies",
    "KnowledgeSearchToolDependencies",
]
