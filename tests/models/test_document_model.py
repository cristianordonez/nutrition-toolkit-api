from __future__ import annotations

from datetime import UTC

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.document import Document


def test_document_schema_and_persistence() -> None:
    table = Document.__table__  # ty: ignore[unresolved-attribute]
    assert set(table.c.keys()) == {
        "id",
        "filename",
        "file_type",
        "checksum",
        "storage_uri",
        "imported_at",
        "document_type",
    }

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document = Document(
        filename="orders.pdf",
        file_type="application/pdf",
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


def test_document_checksum_is_indexed_and_unique() -> None:
    table = Document.__table__  # ty: ignore[unresolved-attribute]
    assert table.c.checksum.index is True
    assert table.c.checksum.unique is True

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    documents = [
        Document(
            filename=filename,
            file_type="application/pdf",
            checksum="sha256:same-content",
            storage_uri=f"file:///{filename}",
            document_type="resident-report",
        )
        for filename in ("first.pdf", "second.pdf")
    ]

    with Session(engine) as session:
        session.add_all(documents)
        with pytest.raises(IntegrityError):
            session.commit()
