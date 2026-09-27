"""Nutrition Care Process note vocabulary shared across application layers."""

from __future__ import annotations

from enum import StrEnum


class NCPNoteType(StrEnum):
    """Supported Nutrition Care Process assessment categories."""

    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    ADMISSION = "admission"
    SIGNIFICANT_CHANGE = "significant_change"


class NCPNoteStatus(StrEnum):
    """Lifecycle and retrieval role of an NCP note."""

    EXAMPLE = "example"
    DRAFT = "draft"
    FINALIZED = "finalized"


__all__ = ["NCPNoteStatus", "NCPNoteType"]
