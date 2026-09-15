"""Private document extractor implementations.

Only concrete classes decorated with ``register_extractor`` are registered::

    PersonExtractor
    ├── PccWeightHistoryExtractor
    ├── PccProgressNotesExtractor
    ├── PccLabResultsExtractor
    ├── WoundReportExtractor
    ├── PccOrderReportExtractor
    └── UnknownFile

Application code must access deterministic extractors through
``PersonIngestionPipeline``.
"""
