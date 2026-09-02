from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.document import Document, DocumentSource, DocumentSourceType
from ntk.models.sql.extracted_fact import ExtractedFact, build_fact_key
from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import (
    ClinicalFactType,
    Resident,
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentWeight,
    ResidentWound,
)


def test_build_fact_key_is_stable_and_generated_on_fact() -> None:
    effective_at = datetime(2026, 8, 27, 12, 30, tzinfo=UTC)
    payload = {"result": 3.0, "name": "Albumin"}
    expected_json = json.dumps(
        {
            "fact_type": "lab",
            "payload": payload,
            "effective_at": effective_at,
        },
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    expected = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()

    fact = ExtractedFact(
        fact_type="lab",
        payload={"name": "Albumin", "result": 3.0},
        effective_at=effective_at,
        confidence=1.0,
    )

    assert fact.fact_key == expected
    assert build_fact_key("lab", payload, effective_at) == expected


def test_only_source_id_references_document_source() -> None:
    table = ExtractedFact.__table__  # ty: ignore[unresolved-attribute]

    assert {key.target_fullname for key in table.c.source_id.foreign_keys} == {
        "document_source.id",
    }
    assert not table.c.source_page.foreign_keys


def test_source_and_fact_key_prevent_duplicate_facts() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document = Document(
        filename="report.pdf",
        file_type="application/pdf",
        checksum="sha256:duplicate",
        storage_uri="file:///report.pdf",
        document_type="resident-report",
    )
    source = DocumentSource(
        document_id=1,
        document=document,
        source_type=DocumentSourceType.PDF,
        source_page=1,
        evidence_hash="a" * 64,
    )
    facts = [
        ExtractedFact(
            source=source,
            fact_type="lab",
            payload={"name": "Albumin", "result": "3.0"},
            confidence=1.0,
        )
        for _ in range(2)
    ]

    with Session(engine) as session:
        session.add_all([document, source, *facts])
        with pytest.raises(IntegrityError):
            session.commit()


def test_document_page_and_evidence_hash_prevent_duplicate_sources() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    document = Document(
        filename="report.pdf",
        file_type="application/pdf",
        checksum="sha256:source-duplicate",
        storage_uri="file:///report.pdf",
        document_type="resident-report",
    )
    sources = [
        DocumentSource(
            document_id=1,
            document=document,
            source_type=DocumentSourceType.PDF,
            source_page=1,
            evidence_hash="b" * 64,
        )
        for _ in range(2)
    ]

    with Session(engine) as session:
        session.add_all([document, *sources])
        with pytest.raises(IntegrityError):
            session.commit()


def test_document_source_fact_and_resident_record_relationships() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    facility = Facility(facility_id="FAC-1", name="Facility")
    resident = Resident(name="Resident")
    document = Document(
        filename="report.pdf",
        file_type="application/pdf",
        checksum="sha256:abc",
        storage_uri="file:///report.pdf",
        document_type="resident-report",
    )
    source = DocumentSource(
        document_id=1,
        document=document,
        source_type=DocumentSourceType.PDF,
        source_page=1,
        evidence_hash="c" * 64,
    )
    fact = ExtractedFact(
        source=source,
        resident=resident,
        fact_type="clinical-records",
        payload={"report": "resident"},
        confidence=1.0,
    )
    records = [
        ResidentWound(
            resident_id=1,
            resident=resident,
            extracted_fact=fact,
            type="Pressure injury",
            location="Sacrum",
            observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
        ResidentLab(
            resident_id=1,
            resident=resident,
            extracted_fact=fact,
            name="Albumin",
            result="3.0",
            observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
        ResidentEdema(
            resident_id=1,
            resident=resident,
            extracted_fact=fact,
            location="Lower extremities",
            severity="2+",
            observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
        ResidentMealIntake(
            resident_id=1,
            resident=resident,
            extracted_fact=fact,
            min_percent=50,
            max_percent=75,
            appetite="Fair",
            observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
        ResidentClinicalFact(
            resident_id=1,
            resident=resident,
            extracted_fact=fact,
            clinical_fact_type=ClinicalFactType.OBSERVATION,
            observation_type="swallowing",
            status="Impaired",
            observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
        ResidentWeight(
            resident_id=1,
            resident=resident,
            extracted_fact=fact,
            weight_lb=130,
        ),
    ]

    with Session(engine) as session:
        session.add_all([facility, resident, document, source, fact, *records])
        session.commit()
        session.refresh(document)
        session.refresh(source)
        session.refresh(fact)

        assert document.sources == [source]
        assert source.extracted_facts == [fact]
        assert fact.resident == resident
        assert fact.wounds == [records[0]]
        assert fact.labs == [records[1]]
        assert fact.edema == [records[2]]
        assert fact.meal_intakes == [records[3]]
        assert fact.clinical_facts == [records[4]]
        assert fact.weights == [records[5]]
