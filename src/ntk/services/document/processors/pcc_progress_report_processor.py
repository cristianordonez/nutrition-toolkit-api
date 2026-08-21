from __future__ import annotations

from ntk.models.document import DocumentType

from .base import PatientDataProcessor
from .pcc_nutrition_assessment_history_processor import (
    PccNutritionAssessmentHistoryProcessor,
)


class PccProgressReportProcessor(
    PccNutritionAssessmentHistoryProcessor,
    PatientDataProcessor,
):
    """Process a PointClickCare Progress Note Report."""

    document_type = DocumentType.PCC_PROGRESS_REPORT
    format_markers = ("progress notes", "note text:", "note text :")

    def extract_patient_data(self) -> None:
        """Extract patient data from a PCC progress report."""
        pass  # noqa: PIE790
