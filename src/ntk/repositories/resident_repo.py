from __future__ import annotations

import hashlib
import typing
from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import SQLModel, col, delete, select

from ntk.models.sql.clinical import (
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentWeight,
    ResidentWound,
)
from ntk.models.sql.document import Document
from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import (
    Resident,
    ResidentAssessment,
    ResidentFacilityStay,
    ResidentIdentifier,
    ResidentProgressNote,
)

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from sqlmodel import Session

    from ntk.services.resident_data.transform import TransformedDocument

ResidentClinicalRecord: typing.TypeAlias = (
    ResidentEdema
    | ResidentLab
    | ResidentOrder
    | ResidentProgressNote
    | ResidentWeight
    | ResidentWound
)
_ResidentEntityT = typing.TypeVar("_ResidentEntityT", bound=SQLModel)
_ConstrainedRecord: typing.TypeAlias = (
    ResidentEdema | ResidentLab | ResidentOrder | ResidentWeight
)

_CONSTRAINED_INCREMENTAL_TYPES = (
    ResidentEdema,
    ResidentLab,
    ResidentOrder,
    ResidentWeight,
)

_RECENT_WEIGHT_LIMIT = 30
_RECENT_LAB_LIMIT = 50
_ACTIVE_ORDER_LIMIT = 50
_RECENT_OBSERVATION_LIMIT = 30
_RECENT_NOTE_LIMIT = 20
_RECENT_CLINICAL_FACT_LIMIT = 50


@dataclass(frozen=True)
class ResidentAssessmentRecords:
    """Bounded persisted records used to construct an assessment prompt."""

    weights: list[ResidentWeight]
    labs: list[ResidentLab]
    orders: list[ResidentOrder]
    progress_notes: list[ResidentProgressNote]
    wounds: list[ResidentWound]
    edema: list[ResidentEdema]
    meal_intakes: list[ResidentMealIntake]
    clinical_facts: list[ResidentClinicalFact]


class ResidentRepo:
    """Persist and retrieve residents and their clinical records."""

    def __init__(self, session: Session) -> None:
        """Get residents from database.

        :param session: database session
        """
        self.session = session

    def get_by_facility_id(self, facility_id: str) -> Resident | None:
        """Get the resident associated with an external facility identifier.

        :param facility_id: external facility identifier
        :return: Resident model or None
        """
        statement = (
            select(Resident)
            .join(
                ResidentFacilityStay,
                col(ResidentFacilityStay.resident_id) == col(Resident.id),
            )
            .join(
                Facility,
                col(Facility.id) == col(ResidentFacilityStay.facility_id),
            )
            .where(Facility.facility_id == facility_id)
        )
        return self.session.exec(statement).first()

    def get_by_id(self, resident_id: int) -> Resident | None:
        """Return a resident by its database identifier."""
        return self.session.get(Resident, resident_id)

    def get_by_name(self, name: str) -> Resident | None:
        """Return a resident using a normalized, case-insensitive name."""
        normalized_name = self._normalize_name(name)
        if not normalized_name:
            return None
        statement = select(Resident).where(
            func.lower(Resident.name) == normalized_name.casefold(),
        )
        return self.session.exec(statement).first()

    def get_by_name_and_date_of_birth(
        self,
        name: str,
        date_of_birth: date,
    ) -> Resident | None:
        """Return a unique resident matching both stable identity fields."""
        normalized_name = self._normalize_name(name)
        if not normalized_name:
            return None
        residents = self.session.exec(
            select(Resident).where(
                func.lower(Resident.name) == normalized_name.casefold(),
                Resident.date_of_birth == date_of_birth,
            ),
        ).all()
        if len(residents) > 1:
            message = (
                f"Resident name {normalized_name!r} and date of birth "
                f"{date_of_birth} are ambiguous"
            )
            raise LookupError(message)
        return residents[0] if residents else None

    def create(self, resident: Resident) -> Resident:
        """Persist a resident or return its normalized-name match."""
        resident.name = self._normalize_name(resident.name)
        resident.sex = self._normalize_sex(resident.sex)
        if not resident.name:
            msg = "Resident name cannot be empty"
            raise ValueError(msg)
        existing = self.get_by_name(resident.name)
        if existing is not None:
            return self.update_demographics(
                existing,
                date_of_birth=resident.date_of_birth,
                sex=resident.sex,
                height_in=resident.height_in,
            )
        return self._persist(resident)

    def create_unmatched(self, resident: Resident) -> Resident:
        """Persist a resident already proven unmatched within its facility."""
        resident.name = self._normalize_name(resident.name)
        resident.sex = self._normalize_sex(resident.sex)
        if not resident.name:
            msg = "Resident name cannot be empty"
            raise ValueError(msg)
        return self._persist(resident)

    def create_for_facility_identifier(
        self,
        resident: Resident,
        *,
        facility_id: int,
        facility_resident_identifier: str,
    ) -> Resident:
        """Atomically create or reuse a facility-scoped resident identity."""
        if resident.id is not None:
            msg = "Resident identity claims require a new resident candidate"
            raise ValueError(msg)
        identifier = facility_resident_identifier.strip()
        if not identifier:
            msg = "Facility resident identifier cannot be empty"
            raise ValueError(msg)
        existing = self.get_by_identifier_mapping(
            facility_id=facility_id,
            facility_resident_identifier=identifier,
        )
        if existing is not None:
            return self.update_demographics(
                existing,
                date_of_birth=resident.date_of_birth,
                sex=resident.sex,
                height_in=resident.height_in,
            )

        resident.name = self._normalize_name(resident.name)
        resident.sex = self._normalize_sex(resident.sex)
        if not resident.name:
            msg = "Resident name cannot be empty"
            raise ValueError(msg)
        demographics = (
            resident.date_of_birth,
            resident.sex,
            resident.height_in,
        )
        self.session.add(resident)
        self.session.flush()
        values = {
            "resident_id": resident.id,
            "facility_id": facility_id,
            "facility_resident_identifier": identifier,
        }
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(ResidentIdentifier)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(ResidentIdentifier)
        else:
            msg = f"Unsupported database dialect for resident identity: {dialect_name}"
            raise RuntimeError(msg)
        self.session.exec(
            statement.values(**values).on_conflict_do_nothing(
                index_elements=[
                    "facility_id",
                    "facility_resident_identifier",
                ],
            ),
        )
        self.session.flush()
        owner = self.get_by_identifier_mapping(
            facility_id=facility_id,
            facility_resident_identifier=identifier,
        )
        if owner is not None and owner.id == resident.id:
            self.session.commit()
            self.session.refresh(resident)
            return resident

        candidate_id = resident.id
        self.session.exec(
            delete(Resident).where(col(Resident.id) == candidate_id),
        )
        self.session.flush()
        existing = self.get_by_identifier_mapping(
            facility_id=facility_id,
            facility_resident_identifier=identifier,
        )
        if existing is None:
            self.session.rollback()
            msg = "Resident identity was claimed but could not be reloaded"
            raise RuntimeError(msg)
        self.session.commit()
        return self.update_demographics(
            existing,
            date_of_birth=demographics[0],
            sex=demographics[1],
            height_in=demographics[2],
        )

    def get_by_identifier_mapping(
        self,
        *,
        facility_id: int,
        facility_resident_identifier: str,
    ) -> Resident | None:
        """Return the resident owning one persisted facility identifier."""
        statement = (
            select(Resident)
            .join(
                ResidentIdentifier,
                col(ResidentIdentifier.resident_id) == col(Resident.id),
            )
            .where(
                ResidentIdentifier.facility_id == facility_id,
                ResidentIdentifier.facility_resident_identifier
                == facility_resident_identifier.strip(),
            )
        )
        return self.session.exec(statement).one_or_none()

    def claim_facility_identifier(
        self,
        resident: Resident,
        *,
        facility_id: int,
        facility_resident_identifier: str,
    ) -> Resident:
        """Atomically associate a new facility identifier with a known resident."""
        resident_id = resident.id
        if resident_id is None:
            msg = "A persisted resident is required to claim an identifier"
            raise ValueError(msg)
        identifier = facility_resident_identifier.strip()
        if not identifier:
            msg = "Facility resident identifier cannot be empty"
            raise ValueError(msg)
        existing = self.get_by_identifier_mapping(
            facility_id=facility_id,
            facility_resident_identifier=identifier,
        )
        if existing is not None:
            return existing
        values = {
            "resident_id": resident_id,
            "facility_id": facility_id,
            "facility_resident_identifier": identifier,
        }
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(ResidentIdentifier)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(ResidentIdentifier)
        else:
            msg = f"Unsupported database dialect for resident identity: {dialect_name}"
            raise RuntimeError(msg)
        self.session.exec(
            statement.values(**values).on_conflict_do_nothing(
                index_elements=[
                    "facility_id",
                    "facility_resident_identifier",
                ],
            ),
        )
        self.session.commit()
        owner = self.get_by_identifier_mapping(
            facility_id=facility_id,
            facility_resident_identifier=identifier,
        )
        if owner is None:
            msg = "Resident identifier claim could not be reloaded"
            raise RuntimeError(msg)
        return owner

    def update_demographics(
        self,
        resident: Resident,
        *,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
    ) -> Resident:
        """Fill missing stable demographics without replacing known values."""
        incoming = {
            "date_of_birth": date_of_birth,
            "sex": self._normalize_sex(sex),
            "height_in": height_in,
        }
        changed = False
        for field_name, value in incoming.items():
            if value is not None and getattr(resident, field_name) is None:
                setattr(resident, field_name, value)
                changed = True
        return self._persist(resident) if changed else resident

    def get_all(self) -> list[Resident]:
        """Return all residents ordered by name and database ID."""
        return list(
            self.session.exec(
                select(Resident).order_by(col(Resident.name), col(Resident.id)),
            ).all(),
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.split())

    @staticmethod
    def _normalize_sex(sex: str | None) -> str | None:
        if sex is None or not sex.strip():
            return None
        normalized = sex.strip().casefold()
        values = {
            "f": "f",
            "female": "f",
            "m": "m",
            "male": "m",
        }
        try:
            return values[normalized]
        except KeyError as error:
            msg = f"Unsupported resident sex: {sex!r}"
            raise ValueError(msg) from error

    def get_assessments_by_resident_ids(
        self,
        resident_ids: Sequence[int],
    ) -> list[ResidentAssessment]:
        """Return assessments belonging to the supplied resident IDs."""
        if not resident_ids:
            return []
        return list(
            self.session.exec(
                select(ResidentAssessment)
                .where(col(ResidentAssessment.resident_id).in_(resident_ids))
                .order_by(
                    col(ResidentAssessment.resident_id),
                    col(ResidentAssessment.created_at).desc(),
                ),
            ).all(),
        )

    def get_weights_by_resident_ids(
        self,
        resident_ids: Sequence[int],
    ) -> list[ResidentWeight]:
        """Return weights belonging to the supplied resident IDs."""
        if not resident_ids:
            return []
        return list(
            self.session.exec(
                select(ResidentWeight)
                .where(col(ResidentWeight.resident_id).in_(resident_ids))
                .order_by(
                    col(ResidentWeight.resident_id),
                    col(ResidentWeight.measured_at).desc(),
                ),
            ).all(),
        )

    def get_clinical_facts_by_resident_ids(
        self,
        resident_ids: Sequence[int],
    ) -> list[ResidentClinicalFact]:
        """Return clinical facts belonging to the supplied resident IDs."""
        if not resident_ids:
            return []
        return list(
            self.session.exec(
                select(ResidentClinicalFact)
                .where(col(ResidentClinicalFact.resident_id).in_(resident_ids))
                .order_by(
                    col(ResidentClinicalFact.resident_id),
                    col(ResidentClinicalFact.observed_at).desc(),
                ),
            ).all(),
        )

    def get_by_resident_id(
        self,
        resident_id: str,
        *,
        facility_name: str | None = None,
    ) -> Resident | None:
        """Return a resident by facility identifier and optional facility name."""
        statement = (
            select(Resident)
            .join(
                ResidentFacilityStay,
                col(ResidentFacilityStay.resident_id) == col(Resident.id),
            )
            .where(
                ResidentFacilityStay.facility_resident_identifier == resident_id,
            )
        )
        if facility_name is not None:
            statement = statement.join(
                Facility,
                col(Facility.id) == col(ResidentFacilityStay.facility_id),
            ).where(
                func.lower(Facility.name) == facility_name.strip().casefold(),
            )
        return self.session.exec(statement).first()

    def get_by_resident_identifier(
        self,
        resident_identifier: str,
        *,
        facility_id: str | None = None,
        resident_name: str | None = None,
    ) -> Resident | None:
        """Resolve an external resident identifier without an unsafe first match.

        ``facility_id`` is the facility's external identifier. When it is omitted,
        the resident identifier must identify exactly one resident across all
        facilities.
        """
        identifier = resident_identifier.strip()
        if not identifier:
            return None
        stay_statement = (
            select(Resident)
            .join(
                ResidentFacilityStay,
                col(ResidentFacilityStay.resident_id) == col(Resident.id),
            )
            .where(
                ResidentFacilityStay.facility_resident_identifier == identifier,
            )
        )
        if facility_id is not None:
            normalized_facility_id = facility_id.strip()
            if not normalized_facility_id:
                return None
            stay_statement = stay_statement.join(
                Facility,
                col(Facility.id) == col(ResidentFacilityStay.facility_id),
            ).where(Facility.facility_id == normalized_facility_id)
            mapped_statement = (
                select(Resident)
                .join(
                    ResidentIdentifier,
                    col(ResidentIdentifier.resident_id) == col(Resident.id),
                )
                .join(
                    Facility,
                    col(Facility.id) == col(ResidentIdentifier.facility_id),
                )
                .where(
                    Facility.facility_id == normalized_facility_id,
                    ResidentIdentifier.facility_resident_identifier == identifier,
                )
            )
        else:
            mapped_statement = (
                select(Resident)
                .join(
                    ResidentIdentifier,
                    col(ResidentIdentifier.resident_id) == col(Resident.id),
                )
                .where(
                    ResidentIdentifier.facility_resident_identifier == identifier,
                )
            )

        fact_statement = (
            select(Resident)
            .join(
                ExtractedFact,
                col(ExtractedFact.resident_id) == col(Resident.id),
            )
            .where(ExtractedFact.facility_resident_identifier == identifier)
        )
        if facility_id is not None:
            fact_statement = fact_statement.join(
                Facility,
                col(Facility.id) == col(ExtractedFact.facility_id),
            ).where(Facility.facility_id == normalized_facility_id)

        residents_by_id = {
            resident.id: resident
            for resident in (
                *self.session.exec(mapped_statement).all(),
                *self.session.exec(stay_statement).all(),
                *self.session.exec(fact_statement).all(),
            )
        }
        if len(residents_by_id) > 1 and resident_name:
            normalized_name = self._normalize_name(resident_name)
            name_matches = {
                resident_id: resident
                for resident_id, resident in residents_by_id.items()
                if self._normalize_name(resident.name).casefold()
                == normalized_name.casefold()
            }
            if len(name_matches) == 1:
                return next(iter(name_matches.values()))
        if len(residents_by_id) > 1:
            scope = " within the provided facility" if facility_id else ""
            message = f"Resident identifier {identifier!r} is ambiguous{scope}"
            raise LookupError(message)
        return next(iter(residents_by_id.values()), None)

    def get_by_name_and_facility(
        self,
        name: str,
        *,
        facility_id: int,
    ) -> Resident | None:
        """Return a unique resident name match within one facility."""
        normalized_name = self._normalize_name(name)
        if not normalized_name:
            return None
        stay_statement = (
            select(Resident)
            .join(ResidentFacilityStay)
            .where(
                ResidentFacilityStay.facility_id == facility_id,
                func.lower(Resident.name) == normalized_name.casefold(),
            )
        )
        fact_statement = (
            select(Resident)
            .join(ExtractedFact)
            .where(
                ExtractedFact.facility_id == facility_id,
                func.lower(Resident.name) == normalized_name.casefold(),
            )
        )
        residents_by_id = {
            resident.id: resident
            for resident in (
                *self.session.exec(stay_statement).all(),
                *self.session.exec(fact_statement).all(),
            )
        }
        if len(residents_by_id) > 1:
            message = (
                f"Resident name {normalized_name!r} is ambiguous within facility "
                f"{facility_id}"
            )
            raise LookupError(message)
        return next(iter(residents_by_id.values()), None)

    def get_assessment_records(self, resident_id: int) -> ResidentAssessmentRecords:
        """Load bounded, reverse-chronological data for assessment generation."""
        weights = list(
            self.session.exec(
                select(ResidentWeight)
                .where(ResidentWeight.resident_id == resident_id)
                .order_by(
                    col(ResidentWeight.measured_at).desc().nulls_last(),
                    col(ResidentWeight.id).desc(),
                )
                .limit(_RECENT_WEIGHT_LIMIT),
            ).all(),
        )
        labs = list(
            self.session.exec(
                select(ResidentLab)
                .where(ResidentLab.resident_id == resident_id)
                .order_by(
                    col(ResidentLab.observed_at).desc(),
                    col(ResidentLab.id).desc(),
                )
                .limit(_RECENT_LAB_LIMIT),
            ).all(),
        )
        orders = list(
            self.session.exec(
                select(ResidentOrder)
                .where(
                    ResidentOrder.resident_id == resident_id,
                    or_(
                        col(ResidentOrder.status).is_(None),
                        func.lower(func.trim(ResidentOrder.status)).in_(
                            ("", "active"),
                        ),
                    ),
                )
                .order_by(
                    col(ResidentOrder.revision_date).desc().nulls_last(),
                    col(ResidentOrder.id).desc(),
                )
                .limit(_ACTIVE_ORDER_LIMIT),
            ).all(),
        )
        progress_notes = list(
            self.session.exec(
                select(ResidentProgressNote)
                .where(ResidentProgressNote.resident_id == resident_id)
                .order_by(
                    col(ResidentProgressNote.note_date).desc(),
                    col(ResidentProgressNote.id).desc(),
                )
                .limit(_RECENT_NOTE_LIMIT),
            ).all(),
        )
        wounds = list(
            self.session.exec(
                select(ResidentWound)
                .where(ResidentWound.resident_id == resident_id)
                .order_by(
                    col(ResidentWound.observed_at).desc().nulls_last(),
                    col(ResidentWound.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        edema = list(
            self.session.exec(
                select(ResidentEdema)
                .where(ResidentEdema.resident_id == resident_id)
                .order_by(
                    col(ResidentEdema.observed_at).desc(),
                    col(ResidentEdema.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        meal_intakes = list(
            self.session.exec(
                select(ResidentMealIntake)
                .where(ResidentMealIntake.resident_id == resident_id)
                .order_by(
                    col(ResidentMealIntake.observed_at).desc(),
                    col(ResidentMealIntake.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        clinical_facts = list(
            self.session.exec(
                select(ResidentClinicalFact)
                .where(ResidentClinicalFact.resident_id == resident_id)
                .order_by(
                    col(ResidentClinicalFact.observed_at).desc(),
                    col(ResidentClinicalFact.id).desc(),
                )
                .limit(_RECENT_CLINICAL_FACT_LIMIT),
            ).all(),
        )
        return ResidentAssessmentRecords(
            weights=weights,
            labs=labs,
            orders=orders,
            progress_notes=progress_notes,
            wounds=wounds,
            edema=edema,
            meal_intakes=meal_intakes,
            clinical_facts=clinical_facts,
        )

    def create_resident(self, resident: Resident) -> Resident:
        """Backward-compatible alias for :meth:`create`."""
        return self.create(resident)

    def create_assessment(
        self,
        assessment: ResidentAssessment,
    ) -> ResidentAssessment:
        """Persist a generated resident assessment."""
        return self._persist(assessment)

    def load_transformed_documents(
        self,
        documents: Sequence[TransformedDocument],
    ) -> None:
        """Persist document provenance and fact graphs atomically."""
        records_by_identity: dict[tuple[object, ...], _ConstrainedRecord] = {}
        try:
            for transformed in documents:
                related_models: list[SQLModel] = []
                for record in transformed.related_models:
                    if isinstance(record, _CONSTRAINED_INCREMENTAL_TYPES):
                        identity = self._record_identity(record)
                        existing_record = records_by_identity.get(identity)
                        if existing_record is None:
                            self._lock_record_identity(record)
                            with self.session.no_autoflush:
                                existing = self._find_existing_record(record)
                            existing_record = typing.cast(
                                "_ConstrainedRecord | None",
                                existing,
                            )
                        if existing_record is not None:
                            relationship_name = self._fact_relationship_name(record)
                            getattr(record.extracted_fact, relationship_name).remove(
                                record,
                            )
                            self._merge_constrained_record(existing_record, record)
                            related_models.append(existing_record)
                            records_by_identity[identity] = existing_record
                            continue
                        records_by_identity[identity] = record
                    if isinstance(record, ResidentWound):
                        with self.session.no_autoflush:
                            existing = self._find_existing_record(record)
                        if existing is not None:
                            record.extracted_fact.wounds.remove(record)
                            self._merge_wound(
                                typing.cast("ResidentWound", existing),
                                record,
                            )
                            related_models.append(existing)
                            continue
                    related_models.append(record)
                self.session.add(transformed.document)
                self.session.add_all(transformed.document_sources)
                self.session.add_all(transformed.extracted_facts)
                self.session.add_all(related_models)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def reconcile_active_order_documents(  # noqa: C901
        self,
        documents: Sequence[TransformedDocument],
    ) -> None:
        """Persist authoritative active-order snapshots in one transaction."""
        try:
            for transformed in documents:
                incoming_orders = self._validated_snapshot_orders(transformed)
                orders_by_scope: dict[tuple[int, int], list[ResidentOrder]] = {}
                seen_by_scope: dict[
                    tuple[int, int],
                    set[tuple[str, date | None]],
                ] = {}

                for order in incoming_orders:
                    extracted_fact = order.extracted_fact
                    facility_id = extracted_fact.facility_id
                    if facility_id is None:
                        msg = "Active-order reconciliation requires a resolved facility"
                        raise ValueError(msg)  # noqa: TRY301
                    scope = (order.resident_id, facility_id)
                    identity = self._active_order_identity(order)
                    seen = seen_by_scope.setdefault(scope, set())
                    if identity in seen:
                        extracted_fact.orders.remove(order)
                        continue
                    seen.add(identity)
                    orders_by_scope.setdefault(scope, []).append(order)
                related_models: list[SQLModel] = [
                    record
                    for record in transformed.related_models
                    if not isinstance(record, ResidentOrder)
                ]
                for scope, orders in orders_by_scope.items():
                    existing_orders = self._orders_for_scope(*scope)
                    existing_by_identity = {
                        self._active_order_identity(order): order
                        for order in existing_orders
                    }
                    incoming_identities = {
                        self._active_order_identity(order) for order in orders
                    }
                    for existing in existing_orders:
                        if (
                            self._is_active_order(existing)
                            and self._active_order_identity(existing)
                            not in incoming_identities
                        ):
                            existing.status = "Inactive"
                            self.session.add(existing)

                    for incoming in orders:
                        identity = self._active_order_identity(incoming)
                        existing = existing_by_identity.get(identity)
                        if existing is None:
                            related_models.append(incoming)
                            continue
                        new_fact = incoming.extracted_fact
                        new_fact.orders.remove(incoming)
                        existing.category = incoming.category
                        existing.status = "Active"
                        existing.supply_last_order_date = (
                            incoming.supply_last_order_date
                        )
                        existing.supply_reorder = incoming.supply_reorder
                        existing.resident_facility_stay_id = (
                            incoming.resident_facility_stay_id
                        )
                        new_fact.orders.append(existing)
                        related_models.append(existing)
                self.session.add(transformed.document)
                self.session.add_all(transformed.document_sources)
                self.session.add_all(transformed.extracted_facts)
                self.session.add_all(related_models)
                self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _validated_snapshot_orders(
        transformed: TransformedDocument,
    ) -> list[ResidentOrder]:
        orders: list[ResidentOrder] = []
        for record in transformed.related_models:
            if not isinstance(record, ResidentOrder):
                msg = "Active-order snapshots may contain only order records"
                raise TypeError(msg)
            if not ResidentRepo._is_active_order(record):
                msg = "Active-order snapshots may contain only active orders"
                raise ValueError(msg)
            if record.resident_id is None:
                msg = "Active-order reconciliation requires a resolved resident"
                raise ValueError(msg)
            orders.append(record)
        if not orders:
            msg = "Refusing to reconcile an empty active-order snapshot"
            raise ValueError(msg)
        return orders

    def _orders_for_scope(
        self,
        resident_id: int,
        facility_id: int,
    ) -> list[ResidentOrder]:
        statement = (
            select(ResidentOrder)
            .join(
                ExtractedFact,
                col(ResidentOrder.extracted_fact_id) == col(ExtractedFact.id),
            )
            .where(
                ResidentOrder.resident_id == resident_id,
                ExtractedFact.facility_id == facility_id,
            )
        )
        return list(self.session.exec(statement).all())

    @staticmethod
    def _active_order_identity(order: ResidentOrder) -> tuple[str, date | None]:
        return (" ".join(order.summary.split()).casefold(), order.revision_date)

    @staticmethod
    def _is_active_order(order: ResidentOrder) -> bool:
        return (order.status or "").strip().casefold() == "active"

    def assign_unlinked_facts_to_stay(
        self,
        stay: ResidentFacilityStay,
    ) -> int:
        """Attach unlinked facts within a stay's facility and date range."""
        if stay.id is None:
            msg = "The resident facility stay must be persisted before assignment"
            raise ValueError(msg)
        statement = select(ExtractedFact).where(
            ExtractedFact.resident_id == stay.resident_id,
            ExtractedFact.facility_id == stay.facility_id,
            col(ExtractedFact.resident_facility_stay_id).is_(None),
        )
        if stay.admitted_at is not None:
            statement = statement.where(
                or_(
                    col(ExtractedFact.effective_at).is_(None),
                    col(ExtractedFact.effective_at) >= stay.admitted_at,
                ),
            )
        if stay.discharged_at is not None:
            statement = statement.where(
                or_(
                    col(ExtractedFact.effective_at).is_(None),
                    col(ExtractedFact.effective_at) <= stay.discharged_at,
                ),
            )
        facts = list(self.session.exec(statement).all())
        relationship_names = (
            "wounds",
            "labs",
            "edema",
            "meal_intakes",
            "orders",
            "clinical_facts",
            "weights",
        )
        for fact in facts:
            fact.resident_facility_stay_id = stay.id
            for relationship_name in relationship_names:
                for record in getattr(fact, relationship_name):
                    if record.resident_facility_stay_id is None:
                        record.resident_facility_stay_id = stay.id
        if facts:
            self.session.add_all(facts)
            self.session.commit()
        return len(facts)

    def document_exists(self, checksum: str) -> bool:
        """Return whether a document with ``checksum`` was already ingested."""
        statement = select(Document.id).where(Document.checksum == checksum)
        return self.session.exec(statement).first() is not None

    def _persist(self, model: _ResidentEntityT) -> _ResidentEntityT:
        """Persist and refresh one SQLModel entity."""
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def _find_existing_record(
        self,
        record: ResidentClinicalRecord,
    ) -> ResidentClinicalRecord | None:
        """Find a clinical row with the same model-specific natural identity."""
        model = type(record)
        fields = self._identity_fields(record)
        statement = select(model).where(
            *(getattr(model, field) == getattr(record, field) for field in fields),
        )
        return self.session.exec(statement).first()

    @classmethod
    def _record_identity(
        cls,
        record: ResidentClinicalRecord,
    ) -> tuple[object, ...]:
        return (
            type(record),
            *(getattr(record, field) for field in cls._identity_fields(record)),
        )

    @staticmethod
    def _identity_fields(  # noqa: PLR0911
        record: ResidentClinicalRecord,
    ) -> tuple[str, ...]:
        if isinstance(record, ResidentWeight):
            if record.measured_at is None:
                return ("resident_id", "source_id", "weight_lb", "description")
            return ("resident_id", "measured_at")
        if isinstance(record, ResidentLab):
            if record.observed_at is None:
                return (
                    "resident_id",
                    "source_id",
                    "name",
                    "result",
                    "unit",
                )
            return ("resident_id", "name", "observed_at")
        if isinstance(record, ResidentOrder):
            return ("resident_id", "summary", "revision_date")
        if isinstance(record, ResidentEdema):
            return ("resident_id", "location", "observed_at")
        if isinstance(record, ResidentProgressNote):
            return ("resident_id", "note_date", "note_type", "author", "note_text")
        if isinstance(record, ResidentWound):
            return ("resident_id", "wound_number", "observed_at")
        return ("resident_id", "source_id", "type", "location")

    @classmethod
    def _merge_wound(
        cls,
        existing: ResidentWound,
        incoming: ResidentWound,
    ) -> None:
        """Fill and merge fields on an existing wound observation."""
        free_text_fields = (
            "assessment_note",
            "physician_orders",
            "physician_orders_notes",
        )
        ordinary_fields = (
            "resident_facility_stay_id",
            "type",
            "location",
            "weeks_in_treatment",
            "progress",
            "stage",
            "size",
        )
        for field_name in ordinary_fields:
            if getattr(existing, field_name) is None:
                value = getattr(incoming, field_name)
                if value is not None:
                    setattr(existing, field_name, value)
        for field_name in free_text_fields:
            setattr(
                existing,
                field_name,
                cls._merge_wound_text(
                    getattr(existing, field_name),
                    getattr(incoming, field_name),
                ),
            )

    @staticmethod
    def _merge_constrained_record(
        existing: _ConstrainedRecord,
        incoming: _ConstrainedRecord,
    ) -> None:
        """Update a natural-key match without inserting a duplicate row."""
        if isinstance(existing, ResidentWeight) and isinstance(
            incoming,
            ResidentWeight,
        ):
            ResidentRepo._merge_weight(existing, incoming)
        elif isinstance(existing, ResidentLab) and isinstance(incoming, ResidentLab):
            ResidentRepo._merge_lab(existing, incoming)
        elif isinstance(existing, ResidentOrder) and isinstance(
            incoming,
            ResidentOrder,
        ):
            ResidentRepo._merge_order(existing, incoming)
        elif isinstance(existing, ResidentEdema) and isinstance(
            incoming,
            ResidentEdema,
        ):
            ResidentRepo._merge_edema(existing, incoming)
        else:
            msg = "Cannot merge different resident record types"
            raise TypeError(msg)
        if (
            existing.resident_facility_stay_id is None
            and incoming.resident_facility_stay_id is not None
        ):
            existing.resident_facility_stay_id = incoming.resident_facility_stay_id

    @staticmethod
    def _merge_weight(existing: ResidentWeight, incoming: ResidentWeight) -> None:
        existing.weight_lb = incoming.weight_lb
        if incoming.description is not None:
            existing.description = incoming.description

    @staticmethod
    def _merge_lab(existing: ResidentLab, incoming: ResidentLab) -> None:
        existing.result = incoming.result
        for field_name in ("unit", "flag", "reference_range"):
            value = getattr(incoming, field_name)
            if value is not None:
                setattr(existing, field_name, value)

    @staticmethod
    def _merge_order(existing: ResidentOrder, incoming: ResidentOrder) -> None:
        for field_name in (
            "category",
            "status",
            "supply_last_order_date",
            "supply_reorder",
        ):
            value = getattr(incoming, field_name)
            if value is not None:
                setattr(existing, field_name, value)

    @staticmethod
    def _merge_edema(existing: ResidentEdema, incoming: ResidentEdema) -> None:
        if incoming.severity is not None:
            existing.severity = incoming.severity

    @staticmethod
    def _fact_relationship_name(record: _ConstrainedRecord) -> str:
        if isinstance(record, ResidentEdema):
            return "edema"
        if isinstance(record, ResidentLab):
            return "labs"
        if isinstance(record, ResidentOrder):
            return "orders"
        return "weights"

    def _lock_record_identity(self, record: _ConstrainedRecord) -> None:
        """Serialize PostgreSQL upserts for one natural record identity."""
        if self.session.get_bind().dialect.name != "postgresql":
            return
        identity = repr(self._record_identity(record))
        lock_key = int.from_bytes(
            hashlib.sha256(identity.encode()).digest()[:8],
            signed=True,
        )
        self.session.exec(select(func.pg_advisory_xact_lock(lock_key))).one()

    @staticmethod
    def _merge_wound_text(existing: str | None, incoming: str | None) -> str | None:
        if existing is None:
            return incoming
        if incoming is None:
            return existing
        normalized_existing = " ".join(existing.split()).casefold()
        normalized_incoming = " ".join(incoming.split()).casefold()
        if normalized_existing == normalized_incoming:
            return existing
        if normalized_existing in normalized_incoming:
            return incoming
        if normalized_incoming in normalized_existing:
            return existing
        return f"{existing}\n{incoming}"
