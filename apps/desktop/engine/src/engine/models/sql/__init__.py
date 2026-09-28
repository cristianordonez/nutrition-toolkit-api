"""Persisted SQLModel tables used by the desktop engine."""

from __future__ import annotations

from .clinical_fact import ClinicalFact, ExtractionMethod
from .clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
    SourceAuthority,
)
from .document import Document
from .enteral_formula import EnteralFormula, EnteralFormulaNutrient
from .facility import Facility
from .knowledge import (
    Knowledge,
    KnowledgeChunk,
    KnowledgeType,
)
from .ncp_note import NCPNote, NCPNoteStatus, NCPNoteType
from .person import Person
from .settings import ApplicationSettings

__all__ = [
    "ApplicationSettings",
    "ClinicalFact",
    "ClinicalSource",
    "ClinicalSourceKind",
    "Document",
    "EnteralFormula",
    "EnteralFormulaNutrient",
    "ExtractionMethod",
    "ExtractionStatus",
    "Facility",
    "Knowledge",
    "KnowledgeChunk",
    "KnowledgeType",
    "NCPNote",
    "NCPNoteStatus",
    "NCPNoteType",
    "Person",
    "SourceAuthority",
]
