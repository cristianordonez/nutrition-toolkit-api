"""Repositories are called on by controllers to retrieve data."""

from __future__ import annotations

from .embedding_repo import EmbeddingRepo
from .food_repo import FoodRepo
from .knowledge_repo import KnowledgeRepo
from .ncp_repo import NCPRepo

__all__ = [
    "EmbeddingRepo",
    "FoodRepo",
    "KnowledgeRepo",
    "NCPRepo",
]
