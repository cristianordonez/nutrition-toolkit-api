from __future__ import annotations

from ntk.models.document import DocumentType

from .base import PatientDataProcessor


class PccWeightHistoryReportProcessor(PatientDataProcessor):
    """Validate a PointClickCare weight-history report."""

    document_type = DocumentType.PCC_WEIGHT_HISTORY_REPORT
    format_markers = ("weight history",)

    def extract_patient_data(self) -> None:
        """Extract patient data from a PCC weight-history report."""
        pass  # noqa: PIE790


class PccOrderListReportProcessor(PatientDataProcessor):
    """Validate a PointClickCare order-list report."""

    document_type = DocumentType.PCC_ORDER_LIST_REPORT
    format_markers = ("order list", "order listing")

    def extract_patient_data(self) -> None:
        """Extract patient data from a PCC order-list report."""
        pass  # noqa: PIE790


class PccWeightVitalsSummaryProcessor(PatientDataProcessor):
    """Validate a PointClickCare weight/vitals summary."""

    document_type = DocumentType.PCC_WEIGHT_VITALS_SUMMARY
    format_markers = ("weight/vitals", "weights and vitals", "vitals summary")

    def extract_patient_data(self) -> None:
        """Extract patient data from a PCC weight/vitals summary."""
        pass  # noqa: PIE790
