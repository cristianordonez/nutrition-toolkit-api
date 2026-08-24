"""Private document extractor implementations.

Only concrete classes decorated with ``register_extractor`` are registered::

    BaseExtractor
    ├── PccWeightHistoryExtractor
    ├── PccProgressNotesExtractor
    ├── PccLabResultsExtractor
    ├── WoundReportExtractor
    ├── PccOrderReportExtractor
    ├── KnowledgeExtractor             (shared, not registered)
    │   ├── NutritionCareManualExtractor
    │   └── DietManualExtractor
    └── MiscExtractor

Application code must access them through ``DocumentExtractorService``.
"""

from __future__ import annotations
