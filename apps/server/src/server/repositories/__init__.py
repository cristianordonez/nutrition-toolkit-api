"""Repositories are called on by controllers to retrieve data."""

from __future__ import annotations

from .embedding_repo import EmbeddingRepo
from .food_repo import FoodRepo
from .ncp_repo import NCPRepo

__all__ = [
    "EmbeddingRepo",
    "FoodRepo",
    "NCPRepo",
]
