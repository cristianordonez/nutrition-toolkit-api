from __future__ import annotations

import asyncio
import logging
import typing
from datetime import UTC, date, datetime

import pymupdf
import pytest
from sqlmodel import Session, SQLModel, create_engine

import engine.models.sql  # noqa: F401
from engine.models.clinical_facts import PersonDiet, PersonMiscOrder
from engine.models.clinical_vocab import ClinicalStatus
from engine.models.extracted_fact_create import (
    DietPayload,
    ExtractedFactCreate,
    MiscOrderPayload,
)
from engine.pipelines.person.ingestion.extract.pcc_order_report import (
    PccOrderReportExtractor,
)
from engine.pipelines.person.ingestion.pipeline import (
    PersonIngestionPipeline,
)
from engine.pipelines.person.ingestion.transformer import (
    ClinicalFactTransformer,
    TransformedDocument,
)
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib

_REVISION_DATE = date(2026, 8, 1)
_OBSERVED_AT = datetime(2026, 9, 1, tzinfo=UTC)
_NEWER_OBSERVED_AT = datetime(2026, 9, 2, tzinfo=UTC)
_LATEST_OBSERVED_AT = datetime(2026, 9, 3, tzinfo=UTC)


def _transform_orders(
    session: Session,
    path: pathlib.Path,
    orders: list[tuple[str, str, str]],
    *,
    observed_at: datetime = _OBSERVED_AT,
) -> TransformedDocument:
    path.write_text(path.name, encoding="utf-8")
    person_service = PersonService(PersonRepo(session))
    facts = [
        ExtractedFactCreate(
            source_person_identifier=identifier,
            source_person_name=source_person_name,
            payload=MiscOrderPayload(
                description=summary,
                source_category="Dietary - Diet",
                status="active",
                observed_at=observed_at,
                source_revision_date=_REVISION_DATE,
            ),
            confidence=1,
        )
        for identifier, source_person_name, summary in orders
    ]
    return ClinicalFactTransformer(person_service).transform(
        path,
        facts,
        extractor_name="PccOrderReportExtractor",
        source_observed_at=observed_at,
    )


def _orders(session: Session) -> list[PersonMiscOrder]:
    return [
        record
        for record in PersonRepo(session).facts.list_records()
        if isinstance(record, PersonMiscOrder)
    ]


def _active_diets(session: Session) -> list[PersonDiet]:
    return [
        record
        for record in PersonRepo(session).facts.list_records()
        if isinstance(record, PersonDiet) and record.status is ClinicalStatus.ACTIVE
    ]


def _transform_diet(
    session: Session,
    path: pathlib.Path,
    *,
    observed_at: datetime,
    diet_type: str = "regular",
    texture: str = "ground",
) -> TransformedDocument:
    """Build one active diet snapshot for the shared test person."""
    path.write_text(path.name, encoding="utf-8")
    transformer = ClinicalFactTransformer(PersonService(PersonRepo(session)))
    return transformer.transform(
        path,
        [
            ExtractedFactCreate(
                source_person_identifier="RES-DIET",
                source_person_name="Diet Person",
                payload=DietPayload(
                    diet_type=diet_type,
                    texture=texture,
                    liquid_consistency="thin",
                    status=ClinicalStatus.ACTIVE,
                    observed_at=observed_at,
                ),
                confidence=1,
            ),
        ],
        extractor_name="PccOrderReportExtractor",
        source_observed_at=observed_at,
    )


def test_active_snapshot_upserts_inserts_and_deactivates_missing_orders(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        first = _transform_orders(
            session,
            tmp_path / "first.pdf",
            [
                ("RES1", "Person One", "Renal diet"),
                ("RES1", "Person One", "Protein supplement"),
            ],
        )
        repository.reconcile_active_order_documents([first])
        original_ids = {order.description: order.id for order in _orders(session)}
        repeated = _transform_orders(
            session,
            tmp_path / "repeated.pdf",
            [
                ("RES1", "Person One", "Renal diet"),
                ("RES1", "Person One", "Protein supplement"),
            ],
        )
        repository.reconcile_active_order_documents([repeated])
        assert {
            order.description: order.id for order in _orders(session)
        } == original_ids

        second = _transform_orders(
            session,
            tmp_path / "second.pdf",
            [
                ("RES1", "Person One", "  RENAL   DIET "),
                ("RES1", "Person One", "Weekly weights"),
            ],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([second])

        stored = {order.description: order for order in _orders(session)}
        renal = next(
            order for order in stored.values() if "renal" in order.description.lower()
        )
        assert renal.id != original_ids["Renal diet"]
        assert renal.status == "active"
        assert stored["Protein supplement"].status == "inactive"
        assert stored["Weekly weights"].status == "active"
        assert len(stored) == 3  # noqa: PLR2004


def test_reconciliation_is_scoped_to_the_person(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        initial = _transform_orders(
            session,
            tmp_path / "all.pdf",
            [
                ("A1", "Person One", "Order A1"),
                ("A2", "Person Two", "Order A2"),
                ("B1", "Person One", "Order B1"),
            ],
        )
        repository.reconcile_active_order_documents([initial])

        person_one_only = _transform_orders(
            session,
            tmp_path / "person-one.pdf",
            [("A1", "Person One", "Replacement A1")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([person_one_only])

        stored = {order.description: order.status for order in _orders(session)}
        assert stored["Order A1"] == "inactive"
        assert stored["Replacement A1"] == "active"
        assert stored["Order A2"] == "active"
        assert stored["Order B1"] == "active"


def test_snapshot_freshness_is_evaluated_per_person(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        repository.reconcile_active_order_documents(
            [
                _transform_orders(
                    session,
                    tmp_path / "person-a-current.pdf",
                    [("A1", "Person One", "Current A")],
                    observed_at=_LATEST_OBSERVED_AT,
                ),
                _transform_orders(
                    session,
                    tmp_path / "person-b-old.pdf",
                    [("B1", "Person Two", "Old B")],
                    observed_at=_OBSERVED_AT,
                ),
            ],
        )

        mixed_snapshot = _transform_orders(
            session,
            tmp_path / "mixed.pdf",
            [
                ("A1", "Person One", "Stale A"),
                ("B1", "Person Two", "Current B"),
            ],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([mixed_snapshot])

        stored = {order.description: order.status for order in _orders(session)}
        assert stored == {
            "Current A": "active",
            "Old B": "inactive",
            "Current B": "active",
        }


def test_snapshot_reuses_the_matching_diet_row(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        initial = _transform_diet(
            session,
            tmp_path / "progress-note.pdf",
            observed_at=_OBSERVED_AT,
        )
        repository.load_transformed_documents([initial])
        original = _active_diets(session)[0]
        original_id = original.id

        snapshot = _transform_diet(
            session,
            tmp_path / "active-orders.pdf",
            observed_at=_NEWER_OBSERVED_AT,
        )
        # A request may already have attached the transformed provenance graph.
        # Reconciliation must inspect and replace duplicates before it can flush.
        repository.reconcile_active_order_documents([snapshot])

        stored = _active_diets(session)
        assert len(stored) == 1
        assert stored[0].id != original_id
        assert stored[0].observed_at == _NEWER_OBSERVED_AT


def test_newer_snapshot_updates_changed_diet_without_adding_a_row(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        initial = _transform_diet(
            session,
            tmp_path / "initial-diet.pdf",
            observed_at=_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([initial])
        original_id = _active_diets(session)[0].id

        changed = _transform_diet(
            session,
            tmp_path / "changed-diet.pdf",
            observed_at=_NEWER_OBSERVED_AT,
            diet_type="renal",
            texture="pureed",
        )
        repository.reconcile_active_order_documents([changed])

        stored = _active_diets(session)
        assert len(stored) == 1
        assert stored[0].id != original_id
        assert stored[0].diet_type == "renal"
        assert stored[0].texture == "pureed"
        assert stored[0].observed_at == _NEWER_OBSERVED_AT


def test_older_snapshot_imported_later_does_not_replace_current_orders(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        current = _transform_orders(
            session,
            tmp_path / "current.pdf",
            [("RES1", "Person One", "Current order")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([current])

        historical = _transform_orders(
            session,
            tmp_path / "historical.pdf",
            [("RES1", "Person One", "Historical order")],
            observed_at=_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([historical])

        assert {order.description: order.status for order in _orders(session)} == {
            "Current order": "active",
        }
        assert historical.clinical_facts == []


def test_reconciliation_rolls_back_when_a_later_snapshot_is_invalid(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        initial = _transform_orders(
            session,
            tmp_path / "initial.pdf",
            [("RES1", "Person One", "Existing order")],
        )
        repository.reconcile_active_order_documents([initial])

        valid = _transform_orders(
            session,
            tmp_path / "valid.pdf",
            [("RES1", "Person One", "New order")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        invalid = _transform_orders(
            session,
            tmp_path / "invalid.pdf",
            [("RES2", "Person Two", "Invalid order")],
        )
        invalid_order = invalid.clinical_facts[0]
        invalid_order.lifecycle_status = ClinicalStatus.INACTIVE.value
        invalid_order.payload = {
            **invalid_order.payload,
            "status": ClinicalStatus.INACTIVE.value,
        }

        with pytest.raises(ValueError, match="only active orders"):
            repository.reconcile_active_order_documents([valid, invalid])

        stored = {order.description: order.status for order in _orders(session)}
        assert stored == {"Existing order": "active"}


def test_unresolved_person_does_not_modify_existing_orders(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = PersonRepo(session)
        initial = _transform_orders(
            session,
            tmp_path / "initial.pdf",
            [("RES1", "Person One", "Existing order")],
        )
        repository.reconcile_active_order_documents([initial])
        unresolved = _transform_orders(
            session,
            tmp_path / "unresolved.pdf",
            [("RES1", "Person One", "Replacement order")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        unresolved_order = unresolved.clinical_facts[0]
        unresolved_order.person_id = None  # ty: ignore[invalid-assignment]

        with pytest.raises(ValueError, match="resolved person"):
            repository.reconcile_active_order_documents([unresolved])

        stored = {order.description: order.status for order in _orders(session)}
        assert stored == {"Existing order": "active"}


def test_a_parser_failure_skips_only_that_file(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [tmp_path / "first.pdf", tmp_path / "second.pdf"]
    for path in paths:
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((20, 40), "Order Listing Report")
            page.insert_text((20, 60), "Order Status: Active")
            document.save(path)

    class Repository:
        load_calls = 0

        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def document_ingestion_is_complete(_checksum: str) -> bool:
            """A document only counts as ingested once it produced facts."""
            return False

        def load_transformed_documents(self, _documents: object) -> None:
            self.load_calls += 1

        def reconcile_active_order_documents(self, _documents: object) -> None:
            self.load_calls += 1

    repository = Repository()

    class Service:
        def __init__(self, person_repository: object) -> None:
            self.repository = person_repository

    service = PersonIngestionPipeline(
        person_service=typing.cast("PersonService", Service(repository)),
    )

    async def extract(
        path: pathlib.Path,
        **_kwargs: object,
    ) -> list[ExtractedFactCreate]:
        if path == paths[1]:
            msg = "parser failed"
            raise ValueError(msg)
        return []

    monkeypatch.setattr(service, "_extract_report", extract)
    monkeypatch.setattr(
        service,
        "_find_extractor",
        PccOrderReportExtractor,
    )

    result = asyncio.run(service.ingest(paths))

    # The first file was saved; the unreadable second file saved nothing and
    # did not stop the run.
    assert repository.load_calls == 1
    assert len(result.documents) == 1


def test_a_file_that_cannot_be_saved_does_not_sink_the_batch(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = [tmp_path / "rejected.pdf", tmp_path / "kept.pdf"]
    for path in paths:
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((20, 40), "Order Listing Report")
            page.insert_text((20, 60), "Order Status: Active")
            document.save(path)

    class Repository:
        saved: typing.ClassVar[list[str]] = []

        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def document_ingestion_is_complete(_checksum: str) -> bool:
            return False

        def reconcile_active_order_documents(self, documents: list[typing.Any]) -> None:
            name = documents[0].document.filename
            if name == "rejected.pdf":
                msg = "Cannot create a person for Jane Example"
                raise ValueError(msg)
            self.saved.append(name)

        load_transformed_documents = reconcile_active_order_documents

    class Service:
        def __init__(self, person_repository: object) -> None:
            self.repository = person_repository

    service = PersonIngestionPipeline(
        person_service=typing.cast("PersonService", Service(Repository())),
    )

    async def extract(
        _path: pathlib.Path,
        **_kwargs: object,
    ) -> list[ExtractedFactCreate]:
        return []

    monkeypatch.setattr(service, "_extract_report", extract)
    monkeypatch.setattr(service, "_find_extractor", PccOrderReportExtractor)

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(service.ingest(paths))

    assert Repository.saved == ["kept.pdf"]
    assert [document.document.filename for document in result.documents] == [
        "kept.pdf",
    ]
    assert "Could not ingest rejected.pdf (ValueError)" in caplog.text
    # The error names the file, never a resident.
    assert "Jane Example" not in caplog.text


def test_facts_that_match_no_resident_skip_only_their_file(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = [tmp_path / "unmatched.pdf", tmp_path / "kept.pdf"]
    for path in paths:
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((20, 40), "Order Listing Report")
            page.insert_text((20, 60), "Order Status: Active")
            document.save(path)

    class Repository:
        saved: typing.ClassVar[list[str]] = []

        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def document_ingestion_is_complete(_checksum: str) -> bool:
            return False

        def reconcile_active_order_documents(
            self,
            documents: list[typing.Any],
        ) -> None:
            self.saved.append(documents[0].document.filename)

        load_transformed_documents = reconcile_active_order_documents

    class Service:
        def __init__(self, person_repository: object) -> None:
            self.repository = person_repository

    service = PersonIngestionPipeline(
        person_service=typing.cast("PersonService", Service(Repository())),
    )
    real_transformer = service._fact_transformer()  # noqa: SLF001

    class Transformer:
        @staticmethod
        def transform(path: pathlib.Path, *args: object, **kwargs: object) -> object:
            if path.name == "unmatched.pdf":
                msg = "Cannot create a person without first name, last name"
                raise ValueError(msg)
            return real_transformer.transform(path, *args, **kwargs)  # ty: ignore[invalid-argument-type]

    async def extract(
        _path: pathlib.Path,
        **_kwargs: object,
    ) -> list[ExtractedFactCreate]:
        return []

    monkeypatch.setattr(service, "_extract_report", extract)
    monkeypatch.setattr(service, "_find_extractor", PccOrderReportExtractor)
    monkeypatch.setattr(service, "_fact_transformer", Transformer)

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(service.ingest(paths))

    assert Repository.saved == ["kept.pdf"]
    assert len(result.documents) == 1
    assert "Could not ingest unmatched.pdf (ValueError)" in caplog.text
