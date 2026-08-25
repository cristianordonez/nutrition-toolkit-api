"""Resident document classifications retained for CLI compatibility."""

from __future__ import annotations

from enum import StrEnum


class ResidentDocumentType(StrEnum):
    """Identify resident-report formats used for structured extraction."""

    PCC_PROGRESS_REPORT = "pcc-progress-report"
    PCC_WEIGHT_HISTORY_REPORT = "pcc-weight-history-report"
    PCC_ORDER_LIST_REPORT = "pcc-order-list-report"
    PCC_WEIGHT_VITALS_SUMMARY = "pcc-weight-vitals-summary"
