"""Repositories are called on by controllers to retrieve data."""

from __future__ import annotations

from .assessment_repo import AssessmentRepo
from .knowledge_repo import KnowledgeRepo
from .resident_repo import ResidentRepo

__all__ = [
    "AssessmentRepo",
    "KnowledgeRepo",
    "ResidentRepo",
]
