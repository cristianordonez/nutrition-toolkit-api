from __future__ import annotations

import warnings
from datetime import UTC, datetime

from ntk.models.sql.document import Document
from ntk.models.sql.person import PersonLab
from ntk.pipelines.person.ingestion.transformer import TransformedDocument


def test_related_models_serialize_using_their_runtime_model() -> None:
    """Do not run heterogeneous SQLModels through every union serializer."""
    transformed = TransformedDocument(
        document=Document(
            filename="labs.pdf",
            file_type="application/pdf",
            checksum="sha256:checksum",
            storage_uri="file:///labs.pdf",
            document_type="PCCLabResultsExtractor",
        ),
        document_sources=[],
        extracted_facts=[],
        related_models=[
            PersonLab(
                person_id=1,
                name="Albumin",
                result="3.2",
                observed_at=datetime(2026, 7, 29, 15, 55, tzinfo=UTC),
            ),
        ],
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        serialized = transformed.model_dump(mode="json")

    assert serialized["related_models"][0]["name"] == "Albumin"
