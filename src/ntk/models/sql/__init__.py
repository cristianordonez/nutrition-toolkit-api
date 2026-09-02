"""Persisted SQLModel tables used by the application."""

from __future__ import annotations

from .api_key import APIKey, APIKeyPermission, Permission
from .clinical import (
    AI_CAPABLE_STRUCTURED_MODELS,
    DETERMINISTIC_FIRST_MODELS,
    ClinicalFactType,
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentWeight,
    ResidentWound,
)
from .document import Document, DocumentSource, DocumentSourceType
from .extracted_fact import ExtractedFact, ExtractionMethod, build_fact_key
from .facility import Facility
from .food import Food, FoodCategory, FoodNutrient, Nutrient
from .knowledge import Knowledge, KnowledgeChunk, KnowledgeChunkEmbedding
from .resident import (
    AssessmentSource,
    Resident,
    ResidentAssessment,
    ResidentAssessmentEmbedding,
    ResidentFacilityStay,
    ResidentIdentifier,
    ResidentProgressNote,
    StatusType,
)
from .user import User, UserHash

__all__ = [
    "AI_CAPABLE_STRUCTURED_MODELS",
    "DETERMINISTIC_FIRST_MODELS",
    "APIKey",
    "APIKeyPermission",
    "AssessmentSource",
    "ClinicalFactType",
    "Document",
    "DocumentSource",
    "DocumentSourceType",
    "ExtractedFact",
    "ExtractionMethod",
    "Facility",
    "Food",
    "FoodCategory",
    "FoodNutrient",
    "Knowledge",
    "KnowledgeChunk",
    "KnowledgeChunkEmbedding",
    "Nutrient",
    "Permission",
    "Resident",
    "ResidentAssessment",
    "ResidentAssessmentEmbedding",
    "ResidentClinicalFact",
    "ResidentEdema",
    "ResidentFacilityStay",
    "ResidentIdentifier",
    "ResidentLab",
    "ResidentMealIntake",
    "ResidentOrder",
    "ResidentProgressNote",
    "ResidentWeight",
    "ResidentWound",
    "StatusType",
    "User",
    "UserHash",
    "build_fact_key",
]
