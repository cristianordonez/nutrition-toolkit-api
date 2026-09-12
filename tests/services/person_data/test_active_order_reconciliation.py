from __future__ import annotations

import asyncio
import typing
from datetime import UTC, date, datetime

import pymupdf
import pytest
from sqlmodel import Session, SQLModel, col, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.models.extracted_fact_create import (
    DietPayload,
    ExtractedFactCreate,
    MiscOrderPayload,
)
from ntk.models.sql.clinical import ClinicalStatus, PersonDiet
from ntk.models.sql.person import PersonMiscOrder
from ntk.pipelines.person.ingestion.extract.pcc_order_report import (
    PccOrderReportExtractor,
)
from ntk.pipelines.person.ingestion.pipeline import (
    PersonIngestionPipeline,
)
from ntk.pipelines.person.ingestion.transformer import (
    ExtractedFactTransformer,
    TransformedDocument,
)
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib

_REVISION_DATE = date(2026, 8, 1)
_OBSERVED_AT = datetime(2026, 9, 1, tzinfo=UTC)
_NEWER_OBSERVED_AT = datetime(2026, 9, 2, tzinfo=UTC)


def _transform_orders(
    session: Session,
    path: pathlib.Path,
    orders: list[tuple[str, str, str, str]],
    *,
    observed_at: datetime = _OBSERVED_AT,
) -> TransformedDocument:
    path.write_text(path.name, encoding="utf-8")
    facility_repository = FacilityRepo(session)
    resolver = FacilityResolver(facility_repository)
    for facility_name in {order[0] for order in orders}:
        resolver.register_trusted(name=facility_name)
    person_service = PersonService(PersonRepo(session), resolver)
    facts = [
        ExtractedFactCreate(
            facility_name=facility_name,
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
        for facility_name, identifier, source_person_name, summary in orders
    ]
    return ExtractedFactTransformer(person_service).transform(
        path,
        facts,
        extractor_name="PccOrderReportExtractor",
        source_observed_at=observed_at,
    )


def _orders(session: Session) -> list[PersonMiscOrder]:
    return list(
        session.exec(
            select(PersonMiscOrder).order_by(col(PersonMiscOrder.id)),
        ).all(),
    )


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
    resolver = FacilityResolver(FacilityRepo(session))
    resolver.register_trusted(name="Facility A")
    transformer = ExtractedFactTransformer(
        PersonService(PersonRepo(session), resolver),
    )
    return transformer.transform(
        path,
        [
            ExtractedFactCreate(
                facility_name="Facility A",
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
                ("Facility A", "RES1", "Person One", "Renal diet"),
                ("Facility A", "RES1", "Person One", "Protein supplement"),
            ],
        )
        repository.reconcile_active_order_documents([first])
        original_ids = {order.description: order.id for order in _orders(session)}
        repeated = _transform_orders(
            session,
            tmp_path / "repeated.pdf",
            [
                ("Facility A", "RES1", "Person One", "Renal diet"),
                ("Facility A", "RES1", "Person One", "Protein supplement"),
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
                ("Facility A", "RES1", "Person One", "  RENAL   DIET "),
                ("Facility A", "RES1", "Person One", "Weekly weights"),
            ],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([second])

        stored = {order.description: order for order in _orders(session)}
        renal = next(
            order for order in stored.values() if "renal" in order.description.lower()
        )
        assert renal.id == original_ids["Renal diet"]
        assert renal.status == "active"
        assert stored["Protein supplement"].status == "inactive"
        assert stored["Weekly weights"].status == "active"
        assert len(stored) == 3  # noqa: PLR2004


def test_reconciliation_is_scoped_to_person_and_facility(
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
                ("Facility A", "A1", "Person One", "Order A1"),
                ("Facility A", "A2", "Person Two", "Order A2"),
                ("Facility B", "B1", "Person One", "Order B1"),
            ],
        )
        repository.reconcile_active_order_documents([initial])

        person_one_only = _transform_orders(
            session,
            tmp_path / "person-one.pdf",
            [("Facility A", "A1", "Person One", "Replacement A1")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([person_one_only])

        stored = {order.description: order.status for order in _orders(session)}
        assert stored["Order A1"] == "inactive"
        assert stored["Replacement A1"] == "active"
        assert stored["Order A2"] == "active"
        assert stored["Order B1"] == "active"


def test_snapshot_reuses_matching_diet_with_unscoped_provenance(
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
        initial.extracted_facts[0].facility_id = None
        repository.load_transformed_documents([initial])
        original = session.exec(select(PersonDiet)).one()
        original_id = original.id

        snapshot = _transform_diet(
            session,
            tmp_path / "active-orders.pdf",
            observed_at=_NEWER_OBSERVED_AT,
        )
        # A request may already have attached the transformed provenance graph.
        # Reconciliation must inspect and replace duplicates before it can flush.
        session.add(snapshot.document)
        assert snapshot.related_models[0] in session
        repository.reconcile_active_order_documents([snapshot])

        stored = session.exec(select(PersonDiet)).one()
        assert stored.id == original_id
        assert stored.observed_at == _NEWER_OBSERVED_AT.replace(tzinfo=None)
        assert stored.extracted_fact.facility_id is not None


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
        original_id = session.exec(select(PersonDiet)).one().id

        changed = _transform_diet(
            session,
            tmp_path / "changed-diet.pdf",
            observed_at=_NEWER_OBSERVED_AT,
            diet_type="renal",
            texture="pureed",
        )
        repository.reconcile_active_order_documents([changed])

        stored = session.exec(select(PersonDiet)).one()
        assert stored.id == original_id
        assert stored.diet_type == "renal"
        assert stored.texture == "pureed"
        assert stored.observed_at == _NEWER_OBSERVED_AT.replace(tzinfo=None)


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
            [("Facility A", "RES1", "Person One", "Current order")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([current])

        historical = _transform_orders(
            session,
            tmp_path / "historical.pdf",
            [("Facility A", "RES1", "Person One", "Historical order")],
            observed_at=_OBSERVED_AT,
        )
        repository.reconcile_active_order_documents([historical])

        assert {order.description: order.status for order in _orders(session)} == {
            "Current order": "active",
        }
        assert len(historical.extracted_facts) == 1


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
            [("Facility A", "RES1", "Person One", "Existing order")],
        )
        repository.reconcile_active_order_documents([initial])

        valid = _transform_orders(
            session,
            tmp_path / "valid.pdf",
            [("Facility A", "RES1", "Person One", "New order")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        invalid = _transform_orders(
            session,
            tmp_path / "invalid.pdf",
            [("Facility A", "RES2", "Person Two", "Invalid order")],
        )
        invalid_order = invalid.related_models[0]
        assert isinstance(invalid_order, PersonMiscOrder)
        invalid_order.status = ClinicalStatus.INACTIVE

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
            [("Facility A", "RES1", "Person One", "Existing order")],
        )
        repository.reconcile_active_order_documents([initial])
        unresolved = _transform_orders(
            session,
            tmp_path / "unresolved.pdf",
            [("Facility A", "RES1", "Person One", "Replacement order")],
            observed_at=_NEWER_OBSERVED_AT,
        )
        unresolved_order = unresolved.related_models[0]
        assert isinstance(unresolved_order, PersonMiscOrder)
        unresolved_order.person_id = None  # ty: ignore[invalid-assignment]

        with pytest.raises(ValueError, match="resolved person"):
            repository.reconcile_active_order_documents([unresolved])

        stored = {order.description: order.status for order in _orders(session)}
        assert stored == {"Existing order": "active"}


def test_parser_failure_before_reconciliation_leaves_repository_untouched(
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

    async def extract(path: pathlib.Path) -> list[ExtractedFactCreate]:
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

    with pytest.raises(ValueError, match="parser failed"):
        asyncio.run(service.ingest(paths))

    assert repository.load_calls == 0
