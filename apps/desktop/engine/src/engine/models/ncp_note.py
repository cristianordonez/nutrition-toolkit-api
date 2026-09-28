"""Nutrition Care Process note vocabulary shared across application layers."""

from __future__ import annotations

from enum import StrEnum


class NCPNoteType(StrEnum):
    """Supported Nutrition Care Process Note categories."""

    ADMISSION = "admission"
    READMISSION = "readmission"
    SIGNIFICANT_CHANGE = "significant_change"
    WOUND = "wound"
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    FOLLOW_UP = "follow_up"
    PAYER_CHANGE = "payer_change"
    HIGH_RISK = "high_risk"


class NCPNoteStatus(StrEnum):
    """Lifecycle and retrieval role of an NCP note."""

    EXAMPLE = "example"
    DRAFT = "draft"
    FINALIZED = "finalized"


__all__ = ["NCPNoteStatus", "NCPNoteType"]
