"""Reusable tools for the on-device nutrition agents.

Two toolsets. The calculators are pure functions over supplied numbers. The
manual lookups search the diet and nutrition-care manuals, which used to live
in the server's pgvector store and now ship inside the application's own
database -- so the agent can consult them with no network and no account.
"""

from __future__ import annotations

from .calculator_tools import CALCULATOR_TOOLSET, CalculatorToolDependencies
from .knowledge_search_tools import (
    KNOWLEDGE_SEARCH_TOOLSET,
    KnowledgeSearchToolDependencies,
    RagSearchInput,
)

__all__ = [
    "CALCULATOR_TOOLSET",
    "KNOWLEDGE_SEARCH_TOOLSET",
    "CalculatorToolDependencies",
    "KnowledgeSearchToolDependencies",
    "RagSearchInput",
]
