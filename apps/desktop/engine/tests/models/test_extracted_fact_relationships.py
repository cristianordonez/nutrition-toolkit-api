"""Persistence relationships for generic clinical sources and facts."""

from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

import engine.models.sql  # noqa: F401
from engine.models.sql.clinical_fact import ClinicalFact
from engine.models.sql.clinical_source import ClinicalSource, ClinicalSourceKind
from engine.models.sql.document import Document
from engine.models.sql.person import Person


def _fact(*, person_id: int, source: ClinicalSource | None) -> ClinicalFact:
    values: dict[str, object] = {
        "person_id": person_id,
        "clinical_source_id": source.id if source is not None else None,
        "fact_type": "weight",
        "payload": {"weight_lb": 140, "measured_at": "2026-08-20T00:00:00Z"},
        "identity_hash": "weight-2026-08-20",
        "content_hash": "weight-content",
    }
    if source is not None:
        values["source"] = source
    return ClinicalFact(**values)  # ty: ignore[invalid-argument-type]


def test_document_source_fact_provenance_round_trips() -> None:
    database = create_engine("sqlite://")
    SQLModel.metadata.create_all(database)

    with Session(database) as session:
        person = Person(name="Doe, Jane", person_identifier="R1")
        document = Document(
            filename="weights.pdf",
            media_type="application/pdf",
            checksum="sha256:weights",
            document_type="weight-report",
        )
        source = ClinicalSource(
            document=document,
            person=person,
            source_kind=ClinicalSourceKind.REPORT_SECTION,
            source_key="weights-page-1",
            content="Weight 140 lb",
        )
        fact = _fact(person_id=1, source=source)
        fact.person = person
        session.add(fact)
        session.commit()

        stored = session.exec(select(ClinicalFact)).one()
        assert stored.source.content == "Weight 140 lb"
        assert stored.source.document.filename == "weights.pdf"
        assert stored.person.person_identifier == "R1"


def test_fact_can_exist_without_a_document_or_source() -> None:
    database = create_engine("sqlite://")
    SQLModel.metadata.create_all(database)

    with Session(database) as session:
        person = Person(name="Doe, Jane", person_identifier="R1")
        session.add(person)
        session.commit()
        session.refresh(person)
        fact = _fact(person_id=person.id, source=None)  # ty: ignore[invalid-argument-type]
        session.add(fact)
        session.commit()

        stored = session.exec(select(ClinicalFact)).one()
        assert stored.clinical_source_id is None
        assert stored.source is None
