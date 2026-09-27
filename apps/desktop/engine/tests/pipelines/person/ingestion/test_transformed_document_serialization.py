from __future__ import annotations

from engine.models.sql.clinical_fact import ClinicalFact
from engine.models.sql.document import Document
from engine.pipelines.person.ingestion.transformer import TransformedDocument


def test_generic_clinical_facts_serialize_their_typed_payload() -> None:
    transformed = TransformedDocument(
        document=Document(
            filename="labs.pdf",
            media_type="application/pdf",
            checksum="sha256:checksum",
            storage_uri="file:///labs.pdf",
            document_type="PCCLabResultsExtractor",
        ),
        clinical_sources=[],
        clinical_facts=[
            ClinicalFact(
                person_id=1,
                fact_type="lab",
                payload={"name": "Albumin", "result": "3.2"},
                identity_hash="identity",
                content_hash="content",
            ),
        ],
    )

    serialized = transformed.model_dump(mode="json")

    assert serialized["clinical_facts"][0]["payload"]["name"] == "Albumin"
