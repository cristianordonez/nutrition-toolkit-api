"""Persisted SQLModel tables used by the application."""

from __future__ import annotations

from .api_key import APIKey, APIKeyPermission, Permission
from .assessment import Assessment, AssessmentEmbedding
from .food import Food, FoodCategory, FoodNutrient, Nutrient
from .knowledge import Knowledge, KnowledgeChunk, KnowledgeChunkEmbedding
from .resident import (
    EdemaData,
    LabResult,
    MedicationData,
    Resident,
    ResidentSnapshot,
    ResidentSnapshotAssessment,
    SupplementData,
    TubeFeedingData,
    WeightHistoryEntry,
    WoundData,
)

__all__ = [
    "APIKey",
    "APIKeyPermission",
    "Assessment",
    "AssessmentEmbedding",
    "EdemaData",
    "Food",
    "FoodCategory",
    "FoodNutrient",
    "Knowledge",
    "KnowledgeChunk",
    "KnowledgeChunkEmbedding",
    "LabResult",
    "MedicationData",
    "Nutrient",
    "Permission",
    "ProgressNote",
    "Resident",
    "ResidentSnapshot",
    "ResidentSnapshotAssessment",
    "SupplementData",
    "TubeFeedingData",
    "WeightHistoryEntry",
    "WoundData",
]
