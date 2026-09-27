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
    KnowledgeChunkEmbedding,
    KnowledgeType,
)
from .ncp_note import NCPNote, NCPNoteStatus, NCPNoteType
from .ncp_note_embedding import NCPNoteEmbedding
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
    "KnowledgeChunkEmbedding",
    "KnowledgeType",
    "NCPNote",
    "NCPNoteEmbedding",
    "NCPNoteStatus",
    "NCPNoteType",
    "Person",
    "SourceAuthority",
]
