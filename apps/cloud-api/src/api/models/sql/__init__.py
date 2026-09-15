"""Persisted SQLModel tables used by the cloud API."""

from __future__ import annotations

from .api_key import APIKey, APIKeyPermission, Permission
from .food import (
    Food,
    FoodCategory,
    FoodNutrient,
    FoodSyncState,
    Nutrient,
    NutrientClassification,
)
from .knowledge import Knowledge, KnowledgeChunk, KnowledgeChunkEmbedding
from .ncp import (
    NutritionCareProcess,
    NutritionCareProcessEmbedding,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
)

__all__ = [
    "APIKey",
    "APIKeyPermission",
    "Food",
    "FoodCategory",
    "FoodNutrient",
    "FoodSyncState",
    "Knowledge",
    "KnowledgeChunk",
    "KnowledgeChunkEmbedding",
    "Nutrient",
    "NutrientClassification",
    "NutritionCareProcess",
    "NutritionCareProcessEmbedding",
    "NutritionCareProcessSource",
    "NutritionCareProcessStatus",
    "NutritionClinicalNoteType",
    "Permission",
]
