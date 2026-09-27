"""Document completion is derived from its clinical-source statuses."""

from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

import engine.models.sql  # noqa: F401
from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
)
from engine.models.sql.document import Document
from engine.pipelines.person.ingestion.transformer import TransformedDocument
from engine.repositories.person_repo import PersonRepo

_CHECKSUM = "sha256:abc123"


def _session() -> Session:
    database = create_engine("sqlite://")
    SQLModel.metadata.create_all(database)
    return Session(database)


def _document() -> Document:
    return Document(
        filename="report.pdf",
        media_type="application/pdf",
        checksum=_CHECKSUM,
        storage_uri="file:///tmp/report.pdf",
        document_type="UnknownFileExtractor",
    )


def _source(status: ExtractionStatus) -> ClinicalSource:
    return ClinicalSource(
        source_kind=ClinicalSourceKind.REPORT_SECTION,
        source_key=f"source-{status.value}",
        content="source text",
        extraction_status=status,
    )


def test_a_document_without_sources_is_not_complete() -> None:
    with _session() as session:
        session.add(_document())
        session.commit()

        assert PersonRepo(session).document_exists(_CHECKSUM) is True
        assert PersonRepo(session).document_ingestion_is_complete(_CHECKSUM) is False


def test_zero_fact_document_marked_not_applicable_is_complete() -> None:
    with _session() as session:
        repository = PersonRepo(session)
        repository.load_transformed_documents(
            [
                TransformedDocument(
                    document=_document(),
                    clinical_sources=[_source(ExtractionStatus.NOT_APPLICABLE)],
                    clinical_facts=[],
                ),
            ],
        )

        assert repository.document_ingestion_is_complete(_CHECKSUM) is True


def test_a_document_with_a_failed_source_is_not_complete() -> None:
    with _session() as session:
        repository = PersonRepo(session)
        repository.load_transformed_documents(
            [
                TransformedDocument(
                    document=_document(),
                    clinical_sources=[_source(ExtractionStatus.FAILED)],
                    clinical_facts=[],
                ),
            ],
        )

        assert repository.document_ingestion_is_complete(_CHECKSUM) is False


def test_an_unknown_document_is_not_complete() -> None:
    with _session() as session:
        assert PersonRepo(session).document_ingestion_is_complete(_CHECKSUM) is False


def test_reingesting_reuses_the_existing_document_row() -> None:
    with _session() as session:
        repository = PersonRepo(session)
        original = _document()
        session.add(original)
        session.commit()
        session.refresh(original)

        source = _source(ExtractionStatus.EXTRACTED)
        repository.load_transformed_documents(
            [
                TransformedDocument(
                    document=_document(),
                    clinical_sources=[source],
                    clinical_facts=[],
                ),
            ],
        )

        documents = session.exec(select(Document)).all()
        assert len(documents) == 1
        assert documents[0].id == original.id
        assert source.document_id == original.id
