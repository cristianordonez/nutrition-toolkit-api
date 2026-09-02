"""Generate nutrition assessments through the assessment agent."""

from __future__ import annotations

import json
import typing
from datetime import UTC, date, datetime
from hashlib import sha256
from itertools import pairwise

from ntk.agents.assessment_agent import ASSESSMENT_MODEL, AssessmentAgent
from ntk.models.sql.resident import (
    AssessmentSource,
    ResidentAssessment,
    StatusType,
)
from ntk.services.embedding_service import EmbeddingService
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel import SQLModel

    from ntk.models.sql.resident import Resident, ResidentFacilityStay
    from ntk.repositories.assessment_repo import AssessmentRepo
    from ntk.repositories.embedding_repo import EmbeddingRepo
    from ntk.repositories.resident_repo import ResidentAssessmentRecords, ResidentRepo


class _ResidentAgentContext:
    """Expose persisted resident data through the assessment-agent contract."""

    def __init__(
        self,
        resident: Resident,
        records: ResidentAssessmentRecords | None = None,
    ) -> None:
        self.resident = resident
        self.records = records

    def llm_payload(self) -> dict[str, object]:
        """Return persisted clinical data relevant to assessment generation."""
        resident = self.resident
        records = self.records
        weights = records.weights if records is not None else resident.weights
        payload: dict[str, object] = {
            "resident_id": resident.id,
            "resident_name": resident.name,
            "date_of_birth": resident.date_of_birth,
            "age": self._calculate_age(resident.date_of_birth),
            "sex": resident.sex,
            "height_in": resident.height_in,
            "weights": self._records(weights),
            "weight_changes": self._weight_changes(weights),
            "labs": self._records(records.labs if records else resident.labs),
            "orders": self._records(records.orders if records else resident.orders),
            "progress_notes": self._records(
                records.progress_notes if records else resident.progress_notes,
            ),
            "wounds": self._records(
                records.wounds if records else resident.wounds,
            ),
            "edema": self._records(records.edema if records else resident.edema),
            "meal_intakes": self._records(
                records.meal_intakes if records else resident.meal_intakes,
            ),
            "clinical_facts": self._records(
                records.clinical_facts if records else resident.clinical_facts,
            ),
        }
        if records is not None:
            payload["context_scope"] = {
                "ordering": "reverse_chronological",
                "orders": "active_or_unspecified_status_only",
                "history": "bounded_recent_records",
            }
        if stay := self._current_stay(resident.facility_stays):
            payload.update(
                resident_facility_stay_id=stay.id,
                facility_id=stay.facility_id,
                facility_resident_identifier=stay.facility_resident_identifier,
                facility_name=stay.facility.name,
            )
        return payload

    @staticmethod
    def _calculate_age(
        date_of_birth: date | None,
        on_date: date | None = None,
    ) -> int | None:
        """Derive age from DOB for the assessment date."""
        if date_of_birth is None:
            return None
        effective_date = on_date or datetime.now(UTC).date()
        return (
            effective_date.year
            - date_of_birth.year
            - (
                (effective_date.month, effective_date.day)
                < (date_of_birth.month, date_of_birth.day)
            )
        )

    @staticmethod
    def _current_stay(
        stays: Sequence[ResidentFacilityStay] | None,
    ) -> ResidentFacilityStay | None:
        """Return the latest stay active today, if one exists."""
        if not stays:
            return None
        today = datetime.now(UTC).date()
        active_stays = [
            stay
            for stay in stays
            if stay is not None
            and (stay.admitted_at is None or stay.admitted_at.date() <= today)
            and (stay.discharged_at is None or stay.discharged_at.date() >= today)
        ]
        return max(
            active_stays,
            key=_ResidentAgentContext._stay_sort_key,
            default=None,
        )

    @staticmethod
    def _stay_sort_key(
        stay: ResidentFacilityStay | None,
    ) -> tuple[date, int]:
        """Return a stable ordering key while accommodating ORM optionality."""
        if stay is None:
            return date.min, -1
        admitted_at = (
            stay.admitted_at.date() if stay.admitted_at is not None else date.min
        )
        return admitted_at, stay.id or -1

    def summary(self, context: str | None = None) -> str:
        """Serialize persisted clinical data for semantic retrieval."""
        payload = self.llm_payload()
        if context:
            payload["context"] = context
        return json.dumps(payload, default=str, separators=(",", ":"))

    @staticmethod
    def _records(
        records: Sequence[SQLModel] | None,
    ) -> list[dict[str, object]]:
        return [
            record.model_dump(
                mode="json",
                exclude={"id", "resident_id", "extracted_fact_id"},
            )
            for record in records or ()
        ]

    @staticmethod
    def _weight_changes(
        weights: Sequence[typing.Any] | None,
    ) -> list[dict[str, object]]:
        """Calculate adjacent changes for reverse-chronological weights."""
        changes: list[dict[str, object]] = []
        ordered = list(weights or ())
        for current, prior in pairwise(ordered):
            if prior.weight_lb == 0:
                continue
            delta = current.weight_lb - prior.weight_lb
            changes.append(
                {
                    "current_measured_at": current.measured_at,
                    "prior_measured_at": prior.measured_at,
                    "change_lb": round(delta, 2),
                    "percent_change": round((delta / prior.weight_lb) * 100, 2),
                },
            )
        return changes


class AssessmentGenerationService:
    """Coordinate assessment generation independently from controllers."""

    def __init__(
        self,
        resident_repository: ResidentRepo,
        assessment_repository: AssessmentRepo,
        embedding_repository: EmbeddingRepo,
    ) -> None:
        """Store repositories used for retrieval and assessment persistence."""
        self.resident_repository = resident_repository
        self.assessment_repository = assessment_repository
        self.embedding_repository = embedding_repository

    async def generate(
        self,
        resident_identifier: str,
        *,
        facility_id: str | None = None,
        context: str | None = None,
    ) -> ResidentAssessment:
        """Resolve an external identifier and generate a draft assessment."""
        resident = self.resident_repository.get_by_resident_identifier(
            resident_identifier,
            facility_id=facility_id,
        )
        if resident is None:
            message = f"Resident {resident_identifier!r} was not found"
            if facility_id is not None:
                message += f" at facility {facility_id!r}"
            raise LookupError(message)
        resident_id = require_id(resident.id)
        records = self.resident_repository.get_assessment_records(resident_id)
        content = await AssessmentAgent(
            embedding_service=EmbeddingService(self.embedding_repository),
        ).run(
            _ResidentAgentContext(resident, records),
            context,
        )
        assessment = ResidentAssessment(
            resident_id=resident_id,
            resident=resident,
            content=content,
            assessment_source=AssessmentSource.GENERATED,
            content_hash=sha256(" ".join(content.split()).encode()).hexdigest(),
            assessment_index=0,
            assessment_date=datetime.now(UTC).date(),
            created_by=ASSESSMENT_MODEL,
            status=StatusType.DRAFT,
            model_name=ASSESSMENT_MODEL,
        )
        return self.assessment_repository.create(assessment)


__all__ = ["AssessmentGenerationService"]
