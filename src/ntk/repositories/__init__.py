"""Repositories are called on by controllers to retrieve data."""

from __future__ import annotations

from .assessment_repo import AssessmentRepo
from .embedding_repo import EmbeddingRepo
from .facility_repo import FacilityRepo
from .knowledge_repo import KnowledgeRepo
from .progress_note_repo import ProgressNoteRepo
from .resident_facility_stay_repo import ResidentFacilityStayRepo
from .resident_repo import ResidentRepo

__all__ = [
    "AssessmentRepo",
    "EmbeddingRepo",
    "FacilityRepo",
    "KnowledgeRepo",
    "ProgressNoteRepo",
    "ResidentFacilityStayRepo",
    "ResidentRepo",
]
