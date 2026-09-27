"""Resident identity and clinical-record queries."""

from __future__ import annotations

import re
import typing
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, select

from engine.models.clinical_fact_registry import hydrate_fact
from engine.models.clinical_facts import (
    ClinicalRecord,
    PersonAllergy,
    PersonAppetiteObservation,
    PersonClinicalFact,
    PersonDiagnosis,
    PersonDialysis,
    PersonDiet,
    PersonEdema,
    PersonEnteralFeeding,
    PersonFluidPlan,
    PersonFoodPreference,
    PersonGIObservation,
    PersonLab,
    PersonMealIntake,
    PersonMedication,
    PersonMiscOrder,
    PersonNutritionGoal,
    PersonOralFeedingStatus,
    PersonParenteralNutrition,
    PersonSupplement,
    PersonWeight,
    PersonWound,
    utc_now,
)
from engine.models.clinical_vocab import ClinicalStatus
from engine.models.sql.clinical_fact import ClinicalFact
from engine.models.sql.clinical_source import (
    ClinicalSource,
    ExtractionStatus,
)
from engine.models.sql.document import Document
from engine.models.sql.person import (
    Person,
    normalize_person_name_part,
    parse_person_name,
)
from engine.repositories.clinical_fact_repo import ClinicalFactRepo
from engine.repositories.clinical_source_repo import ClinicalSourceRepo

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from sqlmodel import Session

    from engine.pipelines.person.ingestion.transformer import TransformedDocument

_PersonEntityT = typing.TypeVar("_PersonEntityT", bound=SQLModel)

_IDENTIFIER_LABEL_RE = re.compile(
    r"^(?:mrn|mr|medical\s+record(?:\s+number)?)\s*[:#]\s*|"
    r"^(?:mrn|mr|medical\s+record(?:\s+number)?)[\s#]+",
    re.IGNORECASE,
)

_RECENT_WEIGHT_LIMIT = 30
_RECENT_LAB_LIMIT = 50
_RECENT_OBSERVATION_LIMIT = 30
_RECENT_NOTE_LIMIT = 20
_RECENT_CLINICAL_FACT_LIMIT = 50
_RECENT_DOMAIN_LIMIT = 50
_ORDER_FACT_TYPES = {
    "medication",
    "enteral_feeding",
    "parenteral_nutrition",
    "fluid_plan",
    "diet",
    "supplement",
    "misc_order",
}


@dataclass(frozen=True)
class PersonClinicalRecords:
    """Bounded typed records used to construct assessment context."""

    weights: list[PersonWeight] = field(default_factory=list)
    labs: list[PersonLab] = field(default_factory=list)
    orders: list[ClinicalRecord] = field(default_factory=list)
    diagnoses: list[PersonDiagnosis] = field(default_factory=list)
    allergies: list[PersonAllergy] = field(default_factory=list)
    medications: list[PersonMedication] = field(default_factory=list)
    diets: list[PersonDiet] = field(default_factory=list)
    enteral_feedings: list[PersonEnteralFeeding] = field(default_factory=list)
    parenteral_nutrition_records: list[PersonParenteralNutrition] = field(
        default_factory=list,
    )
    fluid_plans: list[PersonFluidPlan] = field(default_factory=list)
    supplements: list[PersonSupplement] = field(default_factory=list)
    dialysis_records: list[PersonDialysis] = field(default_factory=list)
    oral_feeding_status_history: list[PersonOralFeedingStatus] = field(
        default_factory=list,
    )
    food_preferences: list[PersonFoodPreference] = field(default_factory=list)
    misc_orders: list[PersonMiscOrder] = field(default_factory=list)
    nutrition_goals: list[PersonNutritionGoal] = field(default_factory=list)
    clinical_notes: list[ClinicalSource] = field(default_factory=list)
    wounds: list[PersonWound] = field(default_factory=list)
    edema: list[PersonEdema] = field(default_factory=list)
    meal_intakes: list[PersonMealIntake] = field(default_factory=list)
    appetite_observations: list[PersonAppetiteObservation] = field(
        default_factory=list,
    )
    gi_observations: list[PersonGIObservation] = field(default_factory=list)
    clinical_facts: list[PersonClinicalFact] = field(default_factory=list)


class PersonRepo:
    """Persist residents and query their generic clinical facts."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.facts = ClinicalFactRepo(session)
        self.sources = ClinicalSourceRepo(session)

    def get_by_id(self, person_id: int) -> Person | None:
        return self.session.get(Person, person_id)

    def get_by_identifier(self, person_identifier: str) -> Person | None:
        identifier = self._normalize_identifier(person_identifier)
        if identifier is None:
            return None
        persons = list(
            self.session.exec(
                select(Person).where(Person.person_identifier == identifier),
            ).all(),
        )
        if len(persons) > 1:
            msg = f"Person identifier {identifier!r} is ambiguous"
            raise LookupError(msg)
        return persons[0] if persons else None

    def assign_identifier(
        self,
        person: Person,
        person_identifier: str,
        *,
        replace: bool = False,
    ) -> Person:
        identifier = self._normalize_identifier(person_identifier)
        if identifier is None:
            raise ValueError("Person identifier cannot be empty")
        existing = self.get_by_identifier(identifier)
        if existing is not None and existing.id != person.id:
            raise ValueError("Person identifier belongs to another person")
        if person.person_identifier == identifier:
            return person
        if person.person_identifier is not None and not replace:
            raise ValueError("Person already has a different identifier")
        person.person_identifier = identifier
        person.updated_at = utc_now()
        return self._persist(person)

    def get_by_name_and_birth_date(
        self,
        first_name: str,
        last_name: str,
        birth_date: date,
    ) -> Person | None:
        normalized_first = normalize_person_name_part(first_name)
        normalized_last = normalize_person_name_part(last_name)
        if not normalized_first or not normalized_last:
            return None
        persons = list(
            self.session.exec(
                select(Person).where(
                    Person.normalized_first_name == normalized_first,
                    Person.normalized_last_name == normalized_last,
                    Person.date_of_birth == birth_date,
                ),
            ).all(),
        )
        if len(persons) > 1:
            msg = (
                f"Person {first_name!r} {last_name!r} and date of birth "
                f"{birth_date} are ambiguous"
            )
            raise LookupError(msg)
        return persons[0] if persons else None

    def get_compatible_by_name(
        self,
        first_name: str,
        last_name: str,
        *,
        birth_date: date | None = None,
        person_identifier: str | None = None,
    ) -> Person | None:
        normalized_first = normalize_person_name_part(first_name)
        normalized_last = normalize_person_name_part(last_name)
        if not normalized_first or not normalized_last:
            return None
        candidates = list(
            self.session.exec(
                select(Person).where(
                    Person.normalized_first_name == normalized_first,
                    Person.normalized_last_name == normalized_last,
                ),
            ).all(),
        )
        identifier = self._normalize_identifier(person_identifier)
        compatible = [
            person
            for person in candidates
            if (
                birth_date is None
                or person.date_of_birth is None
                or person.date_of_birth == birth_date
            )
            and (
                identifier is None
                or person.person_identifier is None
                or person.person_identifier == identifier
            )
        ]
        compatible = self._prefer_confirmed_identity(
            compatible,
            birth_date=birth_date,
            identifier=identifier,
        )
        if len(compatible) > 1:
            raise LookupError(f"Person name {first_name!r} {last_name!r} is ambiguous")
        return compatible[0] if compatible else None

    @staticmethod
    def _prefer_confirmed_identity(
        candidates: list[Person],
        *,
        birth_date: date | None,
        identifier: str | None,
    ) -> list[Person]:
        if len(candidates) <= 1:
            return candidates
        for value, attribute in (
            (birth_date, "date_of_birth"),
            (identifier, "person_identifier"),
        ):
            if value is None:
                continue
            confirmed = [
                person for person in candidates if getattr(person, attribute) == value
            ]
            if len(confirmed) == 1:
                return confirmed
        return candidates

    def create(self, person: Person) -> Person:
        self._normalize_person(person)
        existing = self._find_existing_identity(person)
        if existing is not None:
            return self.update_demographics(
                existing,
                date_of_birth=person.date_of_birth,
                sex=person.sex,
                height_in=person.height_in,
                person_identifier=person.person_identifier,
            )
        try:
            return self._persist(person)
        except IntegrityError:
            self.session.rollback()
            existing = self._find_existing_identity(person)
            if existing is None:
                raise
            return self.update_demographics(
                existing,
                date_of_birth=person.date_of_birth,
                sex=person.sex,
                height_in=person.height_in,
                person_identifier=person.person_identifier,
            )

    def update_demographics(
        self,
        person: Person,
        *,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
        person_identifier: str | None = None,
    ) -> Person:
        incoming = {
            "date_of_birth": date_of_birth,
            "sex": self._normalize_sex(sex),
            "height_in": height_in,
            "person_identifier": self._normalize_identifier(person_identifier),
        }
        changed = False
        for field_name, value in incoming.items():
            if value is not None and getattr(person, field_name) is None:
                setattr(person, field_name, value)
                changed = True
        if changed:
            person.updated_at = utc_now()
            return self._persist(person)
        return person

    def get_all(self) -> list[Person]:
        return list(
            self.session.exec(
                select(Person).order_by(col(Person.name), col(Person.id)),
            ).all(),
        )

    def get_weights_by_person_ids(
        self,
        person_ids: Sequence[int],
    ) -> list[PersonWeight]:
        return typing.cast(
            "list[PersonWeight]",
            self.facts.list_records(person_ids=person_ids, fact_types={"weight"}),
        )

    def get_clinical_facts_by_person_ids(
        self,
        person_ids: Sequence[int],
    ) -> list[PersonClinicalFact]:
        return typing.cast(
            "list[PersonClinicalFact]",
            self.facts.list_records(
                person_ids=person_ids,
                fact_types={"clinical_observation", "clinical_event"},
            ),
        )

    def get_clinical_records(self, person_id: int) -> PersonClinicalRecords:
        rows = self.facts.list_rows(
            person_id=person_id,
            limit=1_000,
            collapse_identities=True,
        )
        grouped: dict[str, list[ClinicalRecord]] = {}
        for row in rows:
            grouped.setdefault(row.fact_type, []).append(hydrate_fact(row))

        weights = typing.cast(
            "list[PersonWeight]",
            grouped.get("weight", [])[:_RECENT_WEIGHT_LIMIT],
        )
        labs = typing.cast(
            "list[PersonLab]",
            grouped.get("lab", [])[:_RECENT_LAB_LIMIT],
        )
        wound_history = typing.cast("list[PersonWound]", grouped.get("wound", []))
        wounds_by_identity: dict[str, PersonWound] = {}
        for wound in wound_history:
            identity = wound.wound_number or f"{wound.type}:{wound.location}"
            wounds_by_identity.setdefault(identity.casefold(), wound)

        def records(
            name: str,
            limit: int = _RECENT_DOMAIN_LIMIT,
        ) -> list[ClinicalRecord]:
            return grouped.get(name, [])[:limit]

        narrative = [
            *records("clinical_observation", _RECENT_CLINICAL_FACT_LIMIT),
            *records("clinical_event", _RECENT_CLINICAL_FACT_LIMIT),
        ]
        narrative.sort(key=self._clinical_sort_key, reverse=True)
        return PersonClinicalRecords(
            weights=weights,
            labs=labs,
            diagnoses=typing.cast("list[PersonDiagnosis]", records("diagnosis")),
            allergies=typing.cast("list[PersonAllergy]", records("allergy")),
            medications=typing.cast("list[PersonMedication]", records("medication")),
            diets=typing.cast("list[PersonDiet]", records("diet")),
            enteral_feedings=typing.cast(
                "list[PersonEnteralFeeding]",
                records("enteral_feeding"),
            ),
            parenteral_nutrition_records=typing.cast(
                "list[PersonParenteralNutrition]",
                records("parenteral_nutrition"),
            ),
            fluid_plans=typing.cast("list[PersonFluidPlan]", records("fluid_plan")),
            supplements=typing.cast("list[PersonSupplement]", records("supplement")),
            dialysis_records=typing.cast(
                "list[PersonDialysis]",
                records("dialysis"),
            ),
            oral_feeding_status_history=typing.cast(
                "list[PersonOralFeedingStatus]",
                records("oral_feeding_status"),
            ),
            food_preferences=typing.cast(
                "list[PersonFoodPreference]",
                records("food_preference"),
            ),
            misc_orders=typing.cast("list[PersonMiscOrder]", records("misc_order")),
            nutrition_goals=typing.cast(
                "list[PersonNutritionGoal]",
                records("nutrition_goal"),
            ),
            clinical_notes=self.sources.list_progress_notes(
                person_id=person_id,
                limit=_RECENT_NOTE_LIMIT,
            ),
            wounds=list(wounds_by_identity.values())[:_RECENT_OBSERVATION_LIMIT],
            edema=typing.cast(
                "list[PersonEdema]",
                records("edema", _RECENT_OBSERVATION_LIMIT),
            ),
            meal_intakes=typing.cast(
                "list[PersonMealIntake]",
                records("meal_intake", _RECENT_OBSERVATION_LIMIT),
            ),
            appetite_observations=typing.cast(
                "list[PersonAppetiteObservation]",
                records("appetite", _RECENT_OBSERVATION_LIMIT),
            ),
            gi_observations=typing.cast(
                "list[PersonGIObservation]",
                records("gi_observation", _RECENT_OBSERVATION_LIMIT),
            ),
            clinical_facts=typing.cast(
                "list[PersonClinicalFact]",
                narrative[:_RECENT_CLINICAL_FACT_LIMIT],
            ),
        )

    def load_transformed_documents(
        self,
        documents: Sequence[TransformedDocument],
    ) -> None:
        try:
            for transformed in documents:
                self._persist_document_graph(transformed)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def reconcile_active_order_documents(
        self,
        documents: Sequence[TransformedDocument],
    ) -> None:
        try:
            for transformed in documents:
                self._reconcile_active_order_document(transformed)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _reconcile_active_order_document(
        self,
        transformed: TransformedDocument,
    ) -> None:
        incoming = transformed.clinical_facts
        if not incoming:
            raise ValueError("Refusing to reconcile an empty active-order snapshot")
        if any(fact.fact_type not in _ORDER_FACT_TYPES for fact in incoming):
            raise TypeError("Active-order snapshots may contain only order facts")
        if any(fact.person_id is None for fact in incoming):
            raise ValueError("Active-order snapshots require a resolved person")
        if any(
            fact.lifecycle_status != ClinicalStatus.ACTIVE.value for fact in incoming
        ):
            raise ValueError("Active-order snapshots may contain only active orders")
        observed_at = transformed.document.source_observed_at
        if observed_at is None:
            raise ValueError("Active-order reconciliation requires a source timestamp")

        person_ids = {fact.person_id for fact in incoming}
        existing = self.facts.list_rows(
            person_ids=sorted(person_ids),
            fact_types=_ORDER_FACT_TYPES,
        )
        accepted_person_ids = {
            person_id
            for person_id in person_ids
            if self._snapshot_is_newer(
                observed_at,
                (fact for fact in existing if fact.person_id == person_id),
            )
        }
        self._discard_transformed_facts_for_people(
            transformed,
            person_ids - accepted_person_ids,
        )

        for fact in existing:
            if (
                fact.person_id in accepted_person_ids
                and fact.lifecycle_status == ClinicalStatus.ACTIVE.value
            ):
                fact.lifecycle_status = ClinicalStatus.INACTIVE.value
                fact.ended_at = observed_at
                payload = dict(fact.payload)
                payload["status"] = ClinicalStatus.INACTIVE.value
                if "discontinued_at" in payload:
                    payload["discontinued_at"] = observed_at.isoformat()
                fact.payload = payload
                fact.updated_at = utc_now()
                self.session.add(fact)
        self._persist_document_graph(transformed)

    @staticmethod
    def _discard_transformed_facts_for_people(
        transformed: TransformedDocument,
        person_ids: set[int],
    ) -> None:
        """Detach stale facts so relationship cascades cannot persist them."""
        if not person_ids:
            return
        for source in transformed.clinical_sources:
            source.facts[:] = [
                fact for fact in source.facts if fact.person_id not in person_ids
            ]
        transformed.clinical_facts = [
            fact
            for fact in transformed.clinical_facts
            if fact.person_id not in person_ids
        ]

    @classmethod
    def _snapshot_is_newer(
        cls,
        observed_at: datetime,
        existing: typing.Iterable[ClinicalFact],
    ) -> bool:
        """Compare a snapshot only with prior orders for the same resident."""
        latest = max(
            (fact.observed_at for fact in existing if fact.observed_at is not None),
            default=None,
        )
        return latest is None or cls._utc_datetime(observed_at) > cls._utc_datetime(
            latest,
        )

    def _persist_document_graph(self, transformed: TransformedDocument) -> None:
        document = self.get_document_by_checksum(transformed.document.checksum)
        if document is None:
            document = transformed.document
            self.session.add(document)
            self.session.flush()
        elif document.source_observed_at is None:
            document.source_observed_at = transformed.document.source_observed_at
            document.updated_at = utc_now()
            self.session.add(document)

        source_map: dict[int, ClinicalSource] = {}
        for source in transformed.clinical_sources:
            # The transformed graph may already link this transient source to
            # its transient document. Do not let the lookup's autoflush try to
            # cascade it onto an existing persistent document before we know
            # whether the source key is already stored.
            with self.session.no_autoflush:
                stored = self.sources.get_by_key(source.source_key)
            if stored is None:
                source.document = document
                source.document_id = document.id
                self.session.add(source)
                self.session.flush()
                stored = source
            elif stored.document_id is None:
                stored.document_id = document.id
                stored.updated_at = utc_now()
                self.session.add(stored)
            source_map[id(source)] = stored

        for fact in transformed.clinical_facts:
            if fact.source is not None:
                stored_source = source_map[id(fact.source)]
                fact.source = stored_source
                fact.clinical_source_id = stored_source.id
            elif fact.clinical_source_id is not None:
                stored_source = self.sources.get_by_id(fact.clinical_source_id)
                if stored_source is None:
                    raise ValueError(
                        f"Clinical source {fact.clinical_source_id} was not found",
                    )
                if stored_source.document_id is None:
                    stored_source.document_id = document.id
                    stored_source.updated_at = utc_now()
                    self.session.add(stored_source)
                if stored_source.person_id not in {None, fact.person_id}:
                    raise ValueError("Clinical fact person does not match its source")
            self.facts.upsert(fact)
        self.session.flush()

    def document_exists(self, checksum: str) -> bool:
        return self.get_document_by_checksum(checksum) is not None

    def document_ingestion_is_complete(self, checksum: str) -> bool:
        document = self.get_document_by_checksum(checksum)
        if document is None or document.id is None:
            return False
        sources = list(
            self.session.exec(
                select(ClinicalSource).where(
                    ClinicalSource.document_id == document.id,
                ),
            ).all(),
        )
        return bool(sources) and all(
            source.extraction_status
            not in {ExtractionStatus.PENDING, ExtractionStatus.FAILED}
            for source in sources
        )

    def get_document_by_checksum(self, checksum: str) -> Document | None:
        return self.session.exec(
            select(Document).where(Document.checksum == checksum),
        ).first()

    def get_person_ids_by_document_checksum(self, checksum: str) -> list[int]:
        statement = (
            select(ClinicalFact.person_id)
            .join(
                ClinicalSource,
                col(ClinicalFact.clinical_source_id) == col(ClinicalSource.id),
            )
            .join(Document, col(ClinicalSource.document_id) == col(Document.id))
            .where(Document.checksum == checksum)
            .distinct()
        )
        return list(self.session.exec(statement).all())

    def _persist(self, model: _PersonEntityT) -> _PersonEntityT:
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    @staticmethod
    def _normalize_identifier(identifier: str | None) -> str | None:
        if identifier is None:
            return None
        collapsed = " ".join(identifier.split())
        return _IDENTIFIER_LABEL_RE.sub("", collapsed) or None

    def _normalize_person(self, person: Person) -> None:
        person.name = " ".join(person.name.split())
        if not person.name:
            raise ValueError("Person name cannot be empty")
        if not person.first_name and not person.last_name:
            person.first_name, person.last_name = parse_person_name(person.name)
        person.normalized_first_name = normalize_person_name_part(person.first_name)
        person.normalized_last_name = normalize_person_name_part(person.last_name)
        person.person_identifier = self._normalize_identifier(person.person_identifier)
        person.sex = self._normalize_sex(person.sex)

    def _find_existing_identity(self, person: Person) -> Person | None:
        if person.person_identifier is not None:
            match = self.get_by_identifier(person.person_identifier)
            if match is not None:
                return match
        if person.date_of_birth is not None and person.first_name and person.last_name:
            return self.get_by_name_and_birth_date(
                person.first_name,
                person.last_name,
                person.date_of_birth,
            )
        return None

    @staticmethod
    def _normalize_sex(sex: str | None) -> str | None:
        if sex is None or not sex.strip():
            return None
        values = {"f": "f", "female": "f", "m": "m", "male": "m"}
        try:
            return values[sex.strip().casefold()]
        except KeyError as error:
            raise ValueError(f"Unsupported person sex: {sex!r}") from error

    @staticmethod
    def _clinical_sort_key(record: ClinicalRecord) -> tuple[datetime, int]:
        value = (
            getattr(record, "observed_at", None)
            or getattr(record, "effective_at", None)
            or record.created_at
            or datetime.min.replace(tzinfo=UTC)
        )
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value, record.id or -1

    @staticmethod
    def _utc_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["PersonClinicalRecords", "PersonRepo"]
