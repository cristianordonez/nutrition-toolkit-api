from __future__ import annotations

import asyncio
import typing
from datetime import date

import pymupdf
import pytest
from sqlmodel import Session, SQLModel, col, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.models.extracted_fact_create import ExtractedFactCreate, OrderPayload
from ntk.models.sql.resident import ResidentOrder
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.resident_data.extract.pcc_order_report import PccOrderReportExtractor
from ntk.services.resident_data.resident_ingestion_service import (
    ResidentIngestionService,
)
from ntk.services.resident_data.resident_resolver import ResidentResolver
from ntk.services.resident_data.transform import (
    ExtractedFactTransformer,
    TransformedDocument,
)

if typing.TYPE_CHECKING:
    import pathlib

_REVISION_DATE = date(2026, 8, 1)


def _transform_orders(
    session: Session,
    path: pathlib.Path,
    orders: list[tuple[str, str, str, str]],
) -> TransformedDocument:
    path.write_text(path.name, encoding="utf-8")
    resolver = ResidentResolver(
        resident_repository=ResidentRepo(session),
        facility_repository=FacilityRepo(session),
        stay_repository=ResidentFacilityStayRepo(session),
    )
    facts = [
        ExtractedFactCreate(
            facility_name=facility_name,
            facility_resident_identifier=identifier,
            resident_name=resident_name,
            payload=OrderPayload(
                summary=summary,
                category="Dietary - Diet",
                status="Active",
                revision_date=_REVISION_DATE,
            ),
            confidence=1,
        )
        for facility_name, identifier, resident_name, summary in orders
    ]
    return ExtractedFactTransformer(resolver).transform(
        path,
        facts,
        extractor_name="PccOrderReportExtractor",
    )


def _orders(session: Session) -> list[ResidentOrder]:
    return list(
        session.exec(select(ResidentOrder).order_by(col(ResidentOrder.id))).all(),
    )


def test_active_snapshot_upserts_inserts_and_deactivates_missing_orders(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ResidentRepo(session)
        first = _transform_orders(
            session,
            tmp_path / "first.pdf",
            [
                ("Facility A", "RES1", "Resident One", "Renal diet"),
                ("Facility A", "RES1", "Resident One", "Protein supplement"),
            ],
        )
        repository.reconcile_active_order_documents([first])
        original_ids = {order.summary: order.id for order in _orders(session)}
        repeated = _transform_orders(
            session,
            tmp_path / "repeated.pdf",
            [
                ("Facility A", "RES1", "Resident One", "Renal diet"),
                ("Facility A", "RES1", "Resident One", "Protein supplement"),
            ],
        )
        repository.reconcile_active_order_documents([repeated])
        assert {order.summary: order.id for order in _orders(session)} == original_ids

        second = _transform_orders(
            session,
            tmp_path / "second.pdf",
            [
                ("Facility A", "RES1", "Resident One", "  RENAL   DIET "),
                ("Facility A", "RES1", "Resident One", "Weekly weights"),
            ],
        )
        repository.reconcile_active_order_documents([second])

        stored = {order.summary: order for order in _orders(session)}
        renal = next(
            order for order in stored.values() if "renal" in order.summary.lower()
        )
        assert renal.id == original_ids["Renal diet"]
        assert renal.status == "Active"
        assert stored["Protein supplement"].status == "Inactive"
        assert stored["Weekly weights"].status == "Active"
        assert len(stored) == 3  # noqa: PLR2004


def test_reconciliation_is_scoped_to_resident_and_facility(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ResidentRepo(session)
        initial = _transform_orders(
            session,
            tmp_path / "all.pdf",
            [
                ("Facility A", "A1", "Resident One", "Order A1"),
                ("Facility A", "A2", "Resident Two", "Order A2"),
                ("Facility B", "B1", "Resident One", "Order B1"),
            ],
        )
        repository.reconcile_active_order_documents([initial])

        resident_one_only = _transform_orders(
            session,
            tmp_path / "resident-one.pdf",
            [("Facility A", "A1", "Resident One", "Replacement A1")],
        )
        repository.reconcile_active_order_documents([resident_one_only])

        stored = {order.summary: order.status for order in _orders(session)}
        assert stored["Order A1"] == "Inactive"
        assert stored["Replacement A1"] == "Active"
        assert stored["Order A2"] == "Active"
        assert stored["Order B1"] == "Active"


def test_reconciliation_rolls_back_when_a_later_snapshot_is_invalid(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ResidentRepo(session)
        initial = _transform_orders(
            session,
            tmp_path / "initial.pdf",
            [("Facility A", "RES1", "Resident One", "Existing order")],
        )
        repository.reconcile_active_order_documents([initial])

        valid = _transform_orders(
            session,
            tmp_path / "valid.pdf",
            [("Facility A", "RES1", "Resident One", "New order")],
        )
        invalid = _transform_orders(
            session,
            tmp_path / "invalid.pdf",
            [("Facility A", "RES2", "Resident Two", "Invalid order")],
        )
        invalid_order = invalid.related_models[0]
        assert isinstance(invalid_order, ResidentOrder)
        invalid_order.status = "Inactive"

        with pytest.raises(ValueError, match="only active orders"):
            repository.reconcile_active_order_documents([valid, invalid])

        stored = {order.summary: order.status for order in _orders(session)}
        assert stored == {"Existing order": "Active"}


def test_unresolved_resident_does_not_modify_existing_orders(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ResidentRepo(session)
        initial = _transform_orders(
            session,
            tmp_path / "initial.pdf",
            [("Facility A", "RES1", "Resident One", "Existing order")],
        )
        repository.reconcile_active_order_documents([initial])
        unresolved = _transform_orders(
            session,
            tmp_path / "unresolved.pdf",
            [("Facility A", "RES1", "Resident One", "Replacement order")],
        )
        unresolved_order = unresolved.related_models[0]
        assert isinstance(unresolved_order, ResidentOrder)
        unresolved_order.resident_id = None  # ty: ignore[invalid-assignment]

        with pytest.raises(ValueError, match="resolved resident"):
            repository.reconcile_active_order_documents([unresolved])

        stored = {order.summary: order.status for order in _orders(session)}
        assert stored == {"Existing order": "Active"}


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

    class Resolver:
        resident_repository = repository

    service = ResidentIngestionService(
        resident_resolver=typing.cast("ResidentResolver", Resolver()),
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
