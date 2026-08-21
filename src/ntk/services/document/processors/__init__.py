"""Document processor hierarchy and public exports.

Quick-reference inheritance tree (arrows point from subclass to parent):

::

    BaseProcessor
    ├── IngestionProcessor
    │   ├── AssessmentProcessor
    │   ├── KnowledgeProcessor
    │   │   ├── DietManualProcessor
    │   │   └── NutritionCareManualProcessor
    │   ├── PccNutritionAssessmentHistoryProcessor
    │   │   └── PccProgressReportProcessor *
    │   └── IngestiblePatientDataProcessor *
    └── PatientDataProcessor
        ├── IngestiblePatientDataProcessor *
        ├── PccProgressReportProcessor *
        ├── PccOrderListReportProcessor
        ├── PccWeightHistoryReportProcessor
        └── PccWeightVitalsSummaryProcessor

``*`` marks multiple inheritance. ``IngestiblePatientDataProcessor`` combines
``IngestionProcessor`` and ``PatientDataProcessor``. ``PccProgressReportProcessor``
combines ``PccNutritionAssessmentHistoryProcessor`` (and therefore ingestion) with
``PatientDataProcessor`` so progress reports can be ingested now and support the
future patient-extraction workflow.
"""

from __future__ import annotations

from .assessment_processor import AssessmentProcessor
from .base import (
    BaseProcessor,
    IngestiblePatientDataProcessor,
    IngestionProcessor,
    PatientDataProcessor,
)
from .knowledge_processor import (
    DietManualProcessor,
    KnowledgeProcessor,
    NutritionCareManualProcessor,
)
from .pcc_nutrition_assessment_history_processor import (
    PccNutritionAssessmentHistoryProcessor,
)
from .pcc_progress_report_processor import PccProgressReportProcessor
from .pcc_weight_report_processor import (
    PccOrderListReportProcessor,
    PccWeightHistoryReportProcessor,
    PccWeightVitalsSummaryProcessor,
)

__all__ = [
    "AssessmentProcessor",
    "BaseProcessor",
    "DietManualProcessor",
    "IngestiblePatientDataProcessor",
    "IngestionProcessor",
    "KnowledgeProcessor",
    "NutritionCareManualProcessor",
    "PatientDataProcessor",
    "PccNutritionAssessmentHistoryProcessor",
    "PccOrderListReportProcessor",
    "PccProgressReportProcessor",
    "PccWeightHistoryReportProcessor",
    "PccWeightVitalsSummaryProcessor",
]
