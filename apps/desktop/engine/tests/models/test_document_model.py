from __future__ import annotations

from datetime import UTC

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from engine.models.sql.document import Document


def test_document_schema_and_persistence() -> None:
    table = Document.__table__  # ty: ignore[unresolved-attribute]
    assert set(table.c.keys()) == {
        "id",
        "facility_id",
        "filename",
        "media_type",
        "checksum",
        "storage_uri",
        "byte_size",
        "imported_at",
        "updated_at",
        "source_observed_at",
        "document_type",
        "document_metadata",
    }

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document = Document(
        filename="orders.pdf",
        media_type="application/pdf",
        checksum="sha256:abc123",
        storage_uri="file:///reports/orders.pdf",
        document_type="pcc-order-report",
    )

    with Session(engine) as session:
        session.add(document)
        session.commit()
        session.refresh(document)

        assert isinstance(document.id, int)
        assert document.imported_at.tzinfo in {None, UTC}


def test_document_checksum_is_indexed_and_unique_within_scope() -> None:
    table = Document.__table__  # ty: ignore[unresolved-attribute]
    assert table.c.checksum.index is True

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    documents = [
        Document(
            filename=filename,
            media_type="application/pdf",
            checksum="sha256:same-content",
            storage_uri=f"file:///{filename}",
            document_type="person-report",
        )
        for filename in ("first.pdf", "second.pdf")
    ]

    with Session(engine) as session:
        session.add_all(documents)
        with pytest.raises(IntegrityError):
            session.commit()
