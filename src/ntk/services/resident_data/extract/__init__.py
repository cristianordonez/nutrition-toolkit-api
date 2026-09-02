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
    └── UnknownFile

Application code must access deterministic extractors through
``ResidentIngestionService``.
"""
