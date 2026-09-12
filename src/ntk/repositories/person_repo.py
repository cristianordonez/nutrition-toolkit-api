from __future__ import annotations

import hashlib
import typing
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, select

from ntk.models.sql.clinical import (
    ClinicalStatus,
    ParenteralNutritionStatus,
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
)
from ntk.models.sql.document import Document, DocumentSource
from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.models.sql.person import (
    Person,
    PersonAssessment,
    PersonProgressNote,
    normalize_person_name_part,
    parse_person_name,
)

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from sqlmodel import Session

    from ntk.pipelines.person.ingestion.transformer import TransformedDocument

PersonClinicalRecord: typing.TypeAlias = (
    PersonAllergy
    | PersonAppetiteObservation
    | PersonDiagnosis
    | PersonDialysis
    | PersonDiet
    | PersonEdema
    | PersonEnteralFeeding
    | PersonFoodPreference
    | PersonFluidPlan
    | PersonGIObservation
    | PersonLab
    | PersonMedication
    | PersonMiscOrder
    | PersonOralFeedingStatus
    | PersonParenteralNutrition
    | PersonProgressNote
    | PersonSupplement
    | PersonWeight
    | PersonNutritionGoal
    | PersonWound
)
_PersonEntityT = typing.TypeVar("_PersonEntityT", bound=SQLModel)
_DomainRecordT = typing.TypeVar("_DomainRecordT", bound=SQLModel)
_ConstrainedRecord: typing.TypeAlias = (
    PersonAllergy
    | PersonDiagnosis
    | PersonDialysis
    | PersonDiet
    | PersonEdema
    | PersonEnteralFeeding
    | PersonFoodPreference
    | PersonFluidPlan
    | PersonLab
    | PersonMedication
    | PersonMiscOrder
    | PersonOralFeedingStatus
    | PersonParenteralNutrition
    | PersonSupplement
    | PersonWeight
    | PersonNutritionGoal
)

_StatefulOrderRecord: typing.TypeAlias = (
    PersonMedication
    | PersonEnteralFeeding
    | PersonParenteralNutrition
    | PersonFluidPlan
    | PersonDiet
    | PersonSupplement
    | PersonMiscOrder
)

_CONSTRAINED_INCREMENTAL_TYPES = (
    PersonAllergy,
    PersonDiagnosis,
    PersonDialysis,
    PersonDiet,
    PersonEdema,
    PersonEnteralFeeding,
    PersonFoodPreference,
    PersonFluidPlan,
    PersonLab,
    PersonMedication,
    PersonMiscOrder,
    PersonOralFeedingStatus,
    PersonParenteralNutrition,
    PersonSupplement,
    PersonWeight,
    PersonNutritionGoal,
)

_ORDER_DOMAIN_TYPES = (
    PersonMedication,
    PersonEnteralFeeding,
    PersonParenteralNutrition,
    PersonFluidPlan,
    PersonDiet,
    PersonSupplement,
    PersonMiscOrder,
)

_RECENT_WEIGHT_LIMIT = 30
_RECENT_LAB_LIMIT = 50
_RECENT_OBSERVATION_LIMIT = 30
_RECENT_NOTE_LIMIT = 20
_RECENT_CLINICAL_FACT_LIMIT = 50
_RECENT_DOMAIN_LIMIT = 50


@dataclass(frozen=True)
class PersonAssessmentRecords:
    """Bounded persisted records used to construct an assessment prompt."""

    weights: list[PersonWeight] = field(default_factory=list)
    labs: list[PersonLab] = field(default_factory=list)
    # Compatibility-only projection; new ingestion never persists generic orders.
    orders: list[SQLModel] = field(default_factory=list)
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
    progress_notes: list[PersonProgressNote] = field(default_factory=list)
    wounds: list[PersonWound] = field(default_factory=list)
    edema: list[PersonEdema] = field(default_factory=list)
    meal_intakes: list[PersonMealIntake] = field(default_factory=list)
    appetite_observations: list[PersonAppetiteObservation] = field(
        default_factory=list,
    )
    gi_observations: list[PersonGIObservation] = field(default_factory=list)
    clinical_facts: list[PersonClinicalFact] = field(default_factory=list)


class PersonRepo:
    """Persist and retrieve persons and their clinical records."""

    def __init__(self, session: Session) -> None:
        """Get persons from database.

        :param session: database session
        """
        self.session = session

    def get_by_id(self, person_id: int) -> Person | None:
        """Return a person by its database identifier."""
        return self.session.get(Person, person_id)

    def get_by_identifier(
        self,
        person_identifier: str,
        *,
        facility_id: int | None = None,
    ) -> Person | None:
        """Resolve the identifier stored directly on a person."""
        identifier = self._normalize_identifier(person_identifier)
        if identifier is None:
            return None
        persons = list(
            self.session.exec(
                select(Person).where(Person.person_identifier == identifier),
            ).all(),
        )
        if facility_id is not None:
            exact = [person for person in persons if person.facility_id == facility_id]
            if exact:
                persons = exact
            else:
                persons = [person for person in persons if person.facility_id is None]
        if len(persons) > 1:
            scope = f" at facility {facility_id}" if facility_id is not None else ""
            msg = f"Person identifier {identifier!r} is ambiguous{scope}"
            raise LookupError(msg)
        return persons[0] if persons else None

    def assign_identifier(
        self,
        person: Person,
        person_identifier: str,
        *,
        replace: bool = False,
    ) -> Person:
        """Assign the person's single normalized external identifier."""
        identifier = self._normalize_identifier(person_identifier)
        if identifier is None:
            message = "Person identifier cannot be empty"
            raise ValueError(message)
        existing_person = self.get_by_identifier(
            identifier,
            facility_id=person.facility_id,
        )
        if existing_person is not None and existing_person.id != person.id:
            message = "Person identifier belongs to another person"
            raise ValueError(message)
        if person.person_identifier == identifier:
            return person
        if person.person_identifier is not None and not replace:
            message = "Person already has a different identifier"
            raise ValueError(message)
        person.person_identifier = identifier
        return self._persist(person)

    def get_by_name_and_birth_date(
        self,
        first_name: str,
        last_name: str,
        birth_date: date,
    ) -> Person | None:
        """Return a unique person matching normalized name parts and DOB."""
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
            message = (
                f"Person {first_name!r} {last_name!r} and date of birth "
                f"{birth_date} are ambiguous"
            )
            raise LookupError(message)
        return persons[0] if persons else None

    def get_compatible_by_name(
        self,
        first_name: str,
        last_name: str,
        *,
        birth_date: date | None = None,
        person_identifier: str | None = None,
        facility_id: int | None = None,
    ) -> Person | None:
        """Return one non-conflicting name match when richer identity is absent."""
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
            if (facility_id is None or person.facility_id in {None, facility_id})
            and (
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
        if len(compatible) > 1:
            message = f"Person name {first_name!r} {last_name!r} is ambiguous"
            raise LookupError(message)
        return compatible[0] if compatible else None

    def create(self, person: Person) -> Person:
        """Persist a person or return its exact natural-identity match."""
        self._normalize_person(person)
        existing = self._find_existing_identity(person)
        if existing is not None:
            return self.update_demographics(
                existing,
                date_of_birth=person.date_of_birth,
                sex=person.sex,
                height_in=person.height_in,
                facility_id=person.facility_id,
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
                facility_id=person.facility_id,
                person_identifier=person.person_identifier,
            )

    def update_demographics(  # noqa: PLR0913
        self,
        person: Person,
        *,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
        facility_id: int | None = None,
        person_identifier: str | None = None,
    ) -> Person:
        """Fill missing stable demographics without replacing known values."""
        incoming = {
            "date_of_birth": date_of_birth,
            "sex": self._normalize_sex(sex),
            "height_in": height_in,
            "facility_id": facility_id,
            "person_identifier": self._normalize_identifier(person_identifier),
        }
        changed = False
        for field_name, value in incoming.items():
            if value is not None and getattr(person, field_name) is None:
                setattr(person, field_name, value)
                changed = True
        return self._persist(person) if changed else person

    def assign_facility(self, person: Person, facility_id: int) -> Person:
        """Set the person's current facility after trusted facility resolution."""
        if person.facility_id == facility_id:
            return person
        person.facility_id = facility_id
        return self._persist(person)

    def get_all(self) -> list[Person]:
        """Return all persons ordered by name and database ID."""
        return list(
            self.session.exec(
                select(Person).order_by(col(Person.name), col(Person.id)),
            ).all(),
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.split())

    @staticmethod
    def _normalize_identifier(identifier: str | None) -> str | None:
        if identifier is None:
            return None
        return " ".join(identifier.split()) or None

    def _normalize_person(self, person: Person) -> None:
        person.name = self._normalize_name(person.name)
        if not person.name:
            msg = "Person name cannot be empty"
            raise ValueError(msg)
        if not person.first_name and not person.last_name:
            person.first_name, person.last_name = parse_person_name(person.name)
        person.normalized_first_name = normalize_person_name_part(
            person.first_name,
        )
        person.normalized_last_name = normalize_person_name_part(
            person.last_name,
        )
        person.person_identifier = self._normalize_identifier(
            person.person_identifier,
        )
        person.sex = self._normalize_sex(person.sex)

    def _find_existing_identity(self, person: Person) -> Person | None:
        if person.person_identifier is not None:
            identifier_match = self.get_by_identifier(
                person.person_identifier,
                facility_id=person.facility_id,
            )
            if identifier_match is not None:
                return identifier_match
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
            msg = f"Unsupported person sex: {sex!r}"
            raise ValueError(msg) from error

    def get_assessments_by_person_ids(
        self,
        person_ids: Sequence[int],
    ) -> list[PersonAssessment]:
        """Return assessments belonging to the supplied person IDs."""
        if not person_ids:
            return []
        return list(
            self.session.exec(
                select(PersonAssessment)
                .where(col(PersonAssessment.person_id).in_(person_ids))
                .order_by(
                    col(PersonAssessment.person_id),
                    col(PersonAssessment.assessment_date).desc(),
                    col(PersonAssessment.created_at).desc(),
                    col(PersonAssessment.id).desc(),
                ),
            ).all(),
        )

    def get_weights_by_person_ids(
        self,
        person_ids: Sequence[int],
    ) -> list[PersonWeight]:
        """Return weights belonging to the supplied person IDs."""
        if not person_ids:
            return []
        return list(
            self.session.exec(
                select(PersonWeight)
                .where(col(PersonWeight.person_id).in_(person_ids))
                .order_by(
                    col(PersonWeight.person_id),
                    col(PersonWeight.measured_at).desc(),
                    col(PersonWeight.id).desc(),
                ),
            ).all(),
        )

    def get_clinical_facts_by_person_ids(
        self,
        person_ids: Sequence[int],
    ) -> list[PersonClinicalFact]:
        """Return clinical facts belonging to the supplied person IDs."""
        if not person_ids:
            return []
        return list(
            self.session.exec(
                select(PersonClinicalFact)
                .where(col(PersonClinicalFact.person_id).in_(person_ids))
                .order_by(
                    col(PersonClinicalFact.person_id),
                    col(PersonClinicalFact.observed_at).desc(),
                ),
            ).all(),
        )

    def get_assessment_records(self, person_id: int) -> PersonAssessmentRecords:
        """Load bounded, reverse-chronological data for assessment generation."""
        weights = list(
            self.session.exec(
                select(PersonWeight)
                .where(PersonWeight.person_id == person_id)
                .order_by(
                    col(PersonWeight.measured_at).desc().nulls_last(),
                    col(PersonWeight.id).desc(),
                )
                .limit(_RECENT_WEIGHT_LIMIT),
            ).all(),
        )
        labs = list(
            self.session.exec(
                select(PersonLab)
                .where(PersonLab.person_id == person_id)
                .order_by(
                    col(PersonLab.observed_at).desc(),
                    col(PersonLab.id).desc(),
                )
                .limit(_RECENT_LAB_LIMIT),
            ).all(),
        )
        progress_notes = list(
            self.session.exec(
                select(PersonProgressNote)
                .where(PersonProgressNote.person_id == person_id)
                .order_by(
                    col(PersonProgressNote.note_date).desc(),
                    col(PersonProgressNote.id).desc(),
                )
                .limit(_RECENT_NOTE_LIMIT),
            ).all(),
        )
        wound_history = list(
            self.session.exec(
                select(PersonWound)
                .where(PersonWound.person_id == person_id)
                .order_by(
                    col(PersonWound.observed_at).desc(),
                    col(PersonWound.id).desc(),
                ),
            ).all(),
        )
        wounds_by_identity: dict[str, PersonWound] = {}
        for wound in wound_history:
            identity = wound.wound_number or f"{wound.type}:{wound.location}"
            wounds_by_identity.setdefault(identity.casefold(), wound)
        wounds = list(wounds_by_identity.values())[:_RECENT_OBSERVATION_LIMIT]
        edema = list(
            self.session.exec(
                select(PersonEdema)
                .where(PersonEdema.person_id == person_id)
                .order_by(
                    col(PersonEdema.observed_at).desc(),
                    col(PersonEdema.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        meal_intakes = list(
            self.session.exec(
                select(PersonMealIntake)
                .where(PersonMealIntake.person_id == person_id)
                .order_by(
                    col(PersonMealIntake.observed_at).desc(),
                    col(PersonMealIntake.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        appetite_observations = list(
            self.session.exec(
                select(PersonAppetiteObservation)
                .where(PersonAppetiteObservation.person_id == person_id)
                .order_by(
                    col(PersonAppetiteObservation.observed_at).desc().nulls_last(),
                    col(PersonAppetiteObservation.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        gi_observations = list(
            self.session.exec(
                select(PersonGIObservation)
                .where(PersonGIObservation.person_id == person_id)
                .order_by(
                    col(PersonGIObservation.observed_at).desc().nulls_last(),
                    col(PersonGIObservation.id).desc(),
                )
                .limit(_RECENT_OBSERVATION_LIMIT),
            ).all(),
        )
        clinical_facts = list(
            self.session.exec(
                select(PersonClinicalFact)
                .where(PersonClinicalFact.person_id == person_id)
                .order_by(
                    col(PersonClinicalFact.observed_at).desc(),
                    col(PersonClinicalFact.id).desc(),
                )
                .limit(_RECENT_CLINICAL_FACT_LIMIT),
            ).all(),
        )
        diagnoses = self._recent_domain_records(PersonDiagnosis, person_id)
        allergies = self._recent_domain_records(PersonAllergy, person_id)
        medications = self._recent_domain_records(PersonMedication, person_id)
        diets = self._recent_domain_records(PersonDiet, person_id)
        enteral_feedings = self._recent_domain_records(
            PersonEnteralFeeding,
            person_id,
        )
        parenteral_nutrition_records = self._recent_domain_records(
            PersonParenteralNutrition,
            person_id,
        )
        fluid_plans = self._recent_domain_records(PersonFluidPlan, person_id)
        supplements = self._recent_domain_records(PersonSupplement, person_id)
        dialysis_records = self._recent_domain_records(
            PersonDialysis,
            person_id,
        )
        oral_feeding_status_history = self._recent_domain_records(
            PersonOralFeedingStatus,
            person_id,
        )
        food_preferences = self._recent_domain_records(
            PersonFoodPreference,
            person_id,
        )
        misc_orders = self._recent_domain_records(PersonMiscOrder, person_id)
        nutrition_goals = self._recent_domain_records(PersonNutritionGoal, person_id)
        return PersonAssessmentRecords(
            weights=weights,
            labs=labs,
            diagnoses=diagnoses,
            allergies=allergies,
            medications=medications,
            diets=diets,
            enteral_feedings=enteral_feedings,
            parenteral_nutrition_records=parenteral_nutrition_records,
            fluid_plans=fluid_plans,
            supplements=supplements,
            dialysis_records=dialysis_records,
            oral_feeding_status_history=oral_feeding_status_history,
            food_preferences=food_preferences,
            misc_orders=misc_orders,
            nutrition_goals=nutrition_goals,
            progress_notes=progress_notes,
            wounds=wounds,
            edema=edema,
            meal_intakes=meal_intakes,
            appetite_observations=appetite_observations,
            gi_observations=gi_observations,
            clinical_facts=clinical_facts,
        )

    def _recent_domain_records(
        self,
        model: type[_DomainRecordT],
        person_id: int,
    ) -> list[_DomainRecordT]:
        """Return bounded domain history ordered only by clinical timestamps."""
        ordering: list[typing.Any] = []
        effective_at = getattr(model, "effective_at", None)
        observed_at = getattr(model, "observed_at", None)
        if observed_at is not None:
            ordering.append(col(observed_at).desc().nulls_last())
        if effective_at is not None:
            ordering.append(col(effective_at).desc().nulls_last())
        typed_model: typing.Any = model
        model_id = typed_model.id
        model_person_id = typed_model.person_id
        ordering.append(col(model_id).desc())
        statement = (
            select(model)
            .where(model_person_id == person_id)
            .order_by(*ordering)
            .limit(_RECENT_DOMAIN_LIMIT)
        )
        return list(self.session.exec(statement).all())

    def create_assessment(
        self,
        assessment: PersonAssessment,
    ) -> PersonAssessment:
        """Persist a generated person assessment."""
        return self._persist(assessment)

    def load_transformed_documents(  # noqa: C901, PLR0912, PLR0915
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
                            if self._incoming_state_is_older(existing_record, record):
                                relationship = getattr(
                                    record.extracted_fact,
                                    relationship_name,
                                )
                                if record in relationship:
                                    relationship.remove(record)
                                related_models.append(existing_record)
                                continue
                            old_fact = existing_record.extracted_fact
                            new_fact = record.extracted_fact
                            old_relationship = getattr(old_fact, relationship_name)
                            new_relationship = getattr(new_fact, relationship_name)
                            if existing_record in old_relationship:
                                old_relationship.remove(existing_record)
                            if record in new_relationship:
                                new_relationship.remove(record)
                            self._merge_constrained_record(existing_record, record)
                            if existing_record not in new_relationship:
                                new_relationship.append(existing_record)
                            related_models.append(existing_record)
                            records_by_identity[identity] = existing_record
                            continue
                        records_by_identity[identity] = record
                    if isinstance(record, PersonWound):
                        with self.session.no_autoflush:
                            existing = self._find_existing_record(record)
                        if existing is not None:
                            record.extracted_fact.wounds.remove(record)
                            self._merge_wound(
                                typing.cast("PersonWound", existing),
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

    def reconcile_active_order_documents(  # noqa: C901, PLR0912, PLR0915
        self,
        documents: Sequence[TransformedDocument],
    ) -> None:
        """Persist authoritative active-order snapshots in one transaction."""
        try:
            for transformed in documents:
                incoming_orders = self._validated_snapshot_orders(transformed)
                snapshot_observed_at = transformed.document.source_observed_at
                if snapshot_observed_at is None:
                    msg = "Active-order reconciliation requires a source timestamp"
                    raise ValueError(msg)  # noqa: TRY301
                if any(
                    order.observed_at != snapshot_observed_at
                    for order in incoming_orders
                ):
                    msg = "Active-order facts must use the document source timestamp"
                    raise ValueError(msg)  # noqa: TRY301
                orders_by_scope: dict[
                    tuple[int, int],
                    list[_StatefulOrderRecord],
                ] = {}
                seen_by_scope: dict[
                    tuple[int, int],
                    set[tuple[type[SQLModel], str]],
                ] = {}

                for order in incoming_orders:
                    extracted_fact = order.extracted_fact
                    facility_id = extracted_fact.facility_id
                    if facility_id is None:
                        msg = "Active-order reconciliation requires a resolved facility"
                        raise ValueError(msg)  # noqa: TRY301
                    scope = (order.person_id, facility_id)
                    identity = self._active_order_identity(order)
                    seen = seen_by_scope.setdefault(scope, set())
                    if identity in seen:
                        self._remove_fact_relationship(order)
                        continue
                    seen.add(identity)
                    orders_by_scope.setdefault(scope, []).append(order)
                related_models: list[SQLModel] = [
                    record
                    for record in transformed.related_models
                    if not isinstance(record, _ORDER_DOMAIN_TYPES)
                ]
                existing_orders_by_person: dict[
                    int,
                    list[tuple[_StatefulOrderRecord, int | None]],
                ] = {}
                for scope, orders in orders_by_scope.items():
                    person_id, facility_id = scope
                    person_orders = existing_orders_by_person.get(person_id)
                    if person_orders is None:
                        # The transformed graph can already be session-pending via
                        # relationship cascades. Inspect persisted state before any
                        # pending duplicate order rows are allowed to autoflush.
                        with self.session.no_autoflush:
                            person_orders = self._orders_for_person(person_id)
                        existing_orders_by_person[person_id] = person_orders
                    existing_orders = [
                        order
                        for order, source_facility_id in person_orders
                        if source_facility_id == facility_id
                    ]
                    latest_observed_at = max(
                        (
                            order.observed_at
                            for order in existing_orders
                            if order.observed_at is not None
                        ),
                        default=None,
                    )
                    if latest_observed_at is not None and self._utc_datetime(
                        snapshot_observed_at,
                    ) <= self._utc_datetime(latest_observed_at):
                        for incoming in orders:
                            self._remove_fact_relationship(incoming)
                        continue
                    existing_by_identity = {
                        self._active_order_identity(order): order
                        for order, _source_facility_id in person_orders
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
                            self._set_order_status(existing, active=False)
                            existing.observed_at = snapshot_observed_at
                            self.session.add(existing)

                    for incoming in orders:
                        identity = self._active_order_identity(incoming)
                        existing = existing_by_identity.get(identity)
                        if existing is None:
                            related_models.append(incoming)
                            continue
                        new_fact = incoming.extracted_fact
                        self._remove_fact_relationship(incoming)
                        if isinstance(existing, PersonDiet) and isinstance(
                            incoming,
                            PersonDiet,
                        ):
                            self._merge_diet(existing, incoming)
                            existing.extracted_fact = new_fact
                        else:
                            self._set_order_status(existing, active=True)
                            existing.observed_at = snapshot_observed_at
                            existing.extracted_fact = new_fact
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
    def _set_order_status(order: _StatefulOrderRecord, *, active: bool) -> None:
        """Apply the lifecycle enum owned by an order domain."""
        if isinstance(order, PersonParenteralNutrition):
            order.status = (
                ParenteralNutritionStatus.ACTIVE
                if active
                else ParenteralNutritionStatus.INACTIVE
            )
            return
        order.status = ClinicalStatus.ACTIVE if active else ClinicalStatus.INACTIVE

    @staticmethod
    def _validated_snapshot_orders(
        transformed: TransformedDocument,
    ) -> list[_StatefulOrderRecord]:
        orders: list[_StatefulOrderRecord] = []
        for record in transformed.related_models:
            if not isinstance(record, _ORDER_DOMAIN_TYPES):
                msg = "Active-order snapshots may contain only order records"
                raise TypeError(msg)
            if not PersonRepo._is_active_order(record):
                msg = "Active-order snapshots may contain only active orders"
                raise ValueError(msg)
            if record.person_id is None:
                msg = "Active-order reconciliation requires a resolved person"
                raise ValueError(msg)
            orders.append(record)
        if not orders:
            msg = "Refusing to reconcile an empty active-order snapshot"
            raise ValueError(msg)
        return orders

    def _orders_for_person(
        self,
        person_id: int,
    ) -> list[tuple[_StatefulOrderRecord, int | None]]:
        """Return order states with the facility of their latest provenance."""
        records: list[tuple[_StatefulOrderRecord, int | None]] = []
        for model in _ORDER_DOMAIN_TYPES:
            statement = (
                select(model, ExtractedFact.facility_id)
                .join(
                    ExtractedFact,
                    col(model.extracted_fact_id) == col(ExtractedFact.id),
                )
                .where(model.person_id == person_id)
            )
            records.extend(
                (typing.cast("_StatefulOrderRecord", record), facility_id)
                for record, facility_id in self.session.exec(statement).all()
            )
        return records

    @staticmethod
    def _active_order_identity(
        order: _StatefulOrderRecord,
    ) -> tuple[type[SQLModel], str]:
        if isinstance(order, PersonDiet):
            # A person has one current diet. A changed diet from a newer
            # authoritative order report replaces that row rather than creating
            # a second identity based on the changed state key.
            return type(order), "current-diet"
        return type(order), order.state_key

    @staticmethod
    def _is_active_order(order: _StatefulOrderRecord) -> bool:
        return (
            getattr(order.status, "value", order.status) == ClinicalStatus.ACTIVE.value
        )

    @staticmethod
    def _utc_datetime(value: datetime) -> datetime:
        """Normalize database datetimes for backend-independent comparison."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def document_exists(self, checksum: str) -> bool:
        """Return whether a document with ``checksum`` was already ingested."""
        statement = select(Document.id).where(Document.checksum == checksum)
        return self.session.exec(statement).first() is not None

    def get_document_by_checksum(self, checksum: str) -> Document | None:
        """Return persisted metadata for one ingested document checksum."""
        statement = select(Document).where(Document.checksum == checksum)
        return self.session.exec(statement).first()

    def get_person_ids_by_document_checksum(self, checksum: str) -> list[int]:
        """Return distinct people associated with one ingested document."""
        statement = (
            select(ExtractedFact.person_id)
            .join(
                DocumentSource,
                col(ExtractedFact.source_id) == col(DocumentSource.id),
            )
            .join(Document, col(DocumentSource.document_id) == col(Document.id))
            .where(
                Document.checksum == checksum,
                col(ExtractedFact.person_id).is_not(None),
            )
            .distinct()
        )
        return [
            person_id
            for person_id in self.session.exec(statement).all()
            if person_id is not None
        ]

    def _persist(self, model: _PersonEntityT) -> _PersonEntityT:
        """Persist and refresh one SQLModel entity."""
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def _find_existing_record(
        self,
        record: PersonClinicalRecord,
    ) -> PersonClinicalRecord | None:
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
        record: PersonClinicalRecord,
    ) -> tuple[object, ...]:
        return (
            type(record),
            *(getattr(record, field) for field in cls._identity_fields(record)),
        )

    @staticmethod
    def _identity_fields(  # noqa: PLR0911
        record: PersonClinicalRecord,
    ) -> tuple[str, ...]:
        if isinstance(
            record,
            (
                *_ORDER_DOMAIN_TYPES,
                PersonAllergy,
                PersonDiagnosis,
                PersonDialysis,
                PersonFoodPreference,
                PersonFluidPlan,
                PersonOralFeedingStatus,
                PersonParenteralNutrition,
                PersonNutritionGoal,
            ),
        ):
            return ("person_id", "state_key")
        if isinstance(record, PersonWeight):
            return ("person_id", "measured_at")
        if isinstance(record, PersonLab):
            if record.observed_at is None:
                return (
                    "person_id",
                    "source_id",
                    "name",
                    "result",
                    "unit",
                )
            return ("person_id", "name", "observed_at")
        if isinstance(record, PersonEdema):
            return ("person_id", "location", "observed_at")
        if isinstance(record, PersonProgressNote):
            return ("person_id", "note_date", "note_type", "author", "note_text")
        if isinstance(record, PersonWound):
            return ("person_id", "wound_number", "observed_at")
        return ("person_id", "source_id", "type", "location")

    @classmethod
    def _merge_wound(
        cls,
        existing: PersonWound,
        incoming: PersonWound,
    ) -> None:
        """Fill and merge fields on an existing wound observation."""
        free_text_fields = (
            "assessment_note",
            "physician_orders",
            "physician_orders_notes",
        )
        ordinary_fields = (
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
        if isinstance(existing, PersonWeight) and isinstance(
            incoming,
            PersonWeight,
        ):
            PersonRepo._merge_weight(existing, incoming)
        elif isinstance(existing, PersonLab) and isinstance(incoming, PersonLab):
            PersonRepo._merge_lab(existing, incoming)
        elif isinstance(existing, PersonEdema) and isinstance(
            incoming,
            PersonEdema,
        ):
            PersonRepo._merge_edema(existing, incoming)
        elif isinstance(existing, PersonDiet) and isinstance(incoming, PersonDiet):
            PersonRepo._merge_diet(existing, incoming)
        elif type(existing) is type(incoming) and hasattr(existing, "state_key"):
            PersonRepo._merge_stateful_record(existing, incoming)
        else:
            msg = "Cannot merge different person record types"
            raise TypeError(msg)

    @staticmethod
    def _merge_weight(existing: PersonWeight, incoming: PersonWeight) -> None:
        existing.weight_lb = incoming.weight_lb
        if incoming.description is not None:
            existing.description = incoming.description

    @staticmethod
    def _merge_lab(existing: PersonLab, incoming: PersonLab) -> None:
        existing.result = incoming.result
        for field_name in ("unit", "flag", "reference_range"):
            value = getattr(incoming, field_name)
            if value is not None:
                setattr(existing, field_name, value)

    @staticmethod
    def _merge_edema(existing: PersonEdema, incoming: PersonEdema) -> None:
        if incoming.severity is not None:
            existing.severity = incoming.severity

    @staticmethod
    def _merge_diet(
        existing: PersonDiet,
        incoming: PersonDiet,
    ) -> None:
        """Replace the resident's current diet with a newer order-report state."""
        existing_observed_at = existing.observed_at
        incoming_observed_at = incoming.observed_at
        if (
            existing_observed_at is not None
            and incoming_observed_at is not None
            and PersonRepo._utc_datetime(incoming_observed_at)
            < PersonRepo._utc_datetime(existing_observed_at)
        ):
            return
        for field_name in (
            "diet_type",
            "texture",
            "liquid_consistency",
            "restrictions",
            "instructions",
            "status",
            "effective_at",
            "discontinued_at",
            "observed_at",
            "state_key",
        ):
            setattr(existing, field_name, getattr(incoming, field_name))
        if incoming.extracted_fact is not None:
            existing.extracted_fact = incoming.extracted_fact
        elif incoming.extracted_fact_id is not None:
            existing.extracted_fact_id = incoming.extracted_fact_id

    @staticmethod
    def _merge_stateful_record(
        existing: _ConstrainedRecord,
        incoming: _ConstrainedRecord,
    ) -> None:
        """Refresh one semantic state only from an equal or newer observation."""
        existing_observed_at = getattr(existing, "observed_at", None)
        incoming_observed_at = getattr(incoming, "observed_at", None)
        if (
            existing_observed_at is not None
            and incoming_observed_at is not None
            and PersonRepo._utc_datetime(incoming_observed_at)
            < PersonRepo._utc_datetime(existing_observed_at)
        ):
            return
        for field_name in (
            "status",
            "observed_at",
            "effective_at",
            "discontinued_at",
        ):
            if not hasattr(existing, field_name):
                continue
            value = getattr(incoming, field_name, None)
            if value is not None:
                setattr(existing, field_name, value)
        # The incoming fact is normally new and therefore has no primary key until
        # the unit of work flushes. Keep the relationship intact so SQLAlchemy can
        # populate the required foreign key after inserting that fact; copying its
        # current ``None`` ID would temporarily invalidate the existing row and can
        # fail during query-invoked autoflush.
        if incoming.extracted_fact is not None:
            existing.extracted_fact = incoming.extracted_fact
        elif incoming.extracted_fact_id is not None:
            existing.extracted_fact_id = incoming.extracted_fact_id

    @staticmethod
    def _incoming_state_is_older(
        existing: _ConstrainedRecord,
        incoming: _ConstrainedRecord,
    ) -> bool:
        """Return whether an incoming semantic state is clinically older."""
        if not (hasattr(existing, "state_key") and hasattr(incoming, "state_key")):
            return False
        existing_observed_at = getattr(existing, "observed_at", None)
        incoming_observed_at = getattr(incoming, "observed_at", None)
        return bool(
            existing_observed_at is not None
            and incoming_observed_at is not None
            and PersonRepo._utc_datetime(incoming_observed_at)
            < PersonRepo._utc_datetime(existing_observed_at),
        )

    @staticmethod
    def _fact_relationship_name(record: _ConstrainedRecord) -> str:
        relationship_by_type = {
            PersonAllergy: "allergies",
            PersonDiagnosis: "diagnoses",
            PersonDialysis: "dialysis_records",
            PersonDiet: "diets",
            PersonEnteralFeeding: "enteral_feedings",
            PersonParenteralNutrition: "parenteral_nutrition_records",
            PersonFluidPlan: "fluid_plans",
            PersonFoodPreference: "food_preferences",
            PersonMedication: "medications",
            PersonMiscOrder: "misc_orders",
            PersonOralFeedingStatus: "oral_feeding_status_history",
            PersonSupplement: "supplements",
            PersonNutritionGoal: "nutrition_goals",
        }
        relationship_name = relationship_by_type.get(type(record))
        if relationship_name is not None:
            return relationship_name
        if isinstance(record, PersonEdema):
            return "edema"
        if isinstance(record, PersonLab):
            return "labs"
        return "weights"

    def _remove_fact_relationship(self, record: _ConstrainedRecord) -> None:
        """Detach an incoming domain row that reconciliation has superseded."""
        relationship_name = self._fact_relationship_name(record)
        relationship = getattr(record.extracted_fact, relationship_name)
        if record in relationship:
            relationship.remove(record)
        if record in self.session.new:
            self.session.expunge(record)

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
