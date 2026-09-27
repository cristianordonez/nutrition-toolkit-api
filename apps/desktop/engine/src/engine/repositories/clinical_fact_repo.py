"""Generic clinical fact persistence and typed hydration."""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from sqlmodel import col, select

from engine.models.clinical_fact_registry import hydrate_fact
from engine.models.clinical_facts import PersonClinicalRecord, utc_now
from engine.models.sql.clinical_fact import ClinicalFact, ExtractionMethod

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlmodel import Session


class ClinicalFactRepo:
    """Persist generic facts and return their typed domain representations."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an existing unit-of-work session."""
        self.session = session

    def upsert(self, fact: ClinicalFact) -> ClinicalFact:
        """Insert a fact assertion or update its matching source assertion."""
        statement = select(ClinicalFact).where(
            ClinicalFact.fact_type == fact.fact_type,
            ClinicalFact.identity_hash == fact.identity_hash,
        )
        if fact.clinical_source_id is None:
            statement = statement.where(
                ClinicalFact.person_id == fact.person_id,
                col(ClinicalFact.clinical_source_id).is_(None),
            )
        else:
            statement = statement.where(
                ClinicalFact.clinical_source_id == fact.clinical_source_id,
            )
        existing = self.session.exec(statement).first()
        if existing is None:
            self.session.add(fact)
            return fact
        if self._incoming_wins(existing, fact):
            for field_name in (
                "payload",
                "payload_schema_version",
                "effective_at",
                "observed_at",
                "ended_at",
                "lifecycle_status",
                "concept_key",
                "content_hash",
                "extraction_method",
                "confidence",
                "confidence_reason",
                "model_name",
                "extractor_name",
                "extractor_version",
            ):
                setattr(existing, field_name, getattr(fact, field_name))
            existing.updated_at = utc_now()
            self.session.add(existing)
        return existing

    def upsert_all(self, facts: Iterable[ClinicalFact]) -> list[ClinicalFact]:
        """Upsert all fact assertions without committing the shared session."""
        return [self.upsert(fact) for fact in facts]

    def list_rows(
        self,
        *,
        person_id: int | None = None,
        person_ids: Sequence[int] | None = None,
        fact_types: set[str] | None = None,
        limit: int | None = None,
        collapse_identities: bool = False,
    ) -> list[ClinicalFact]:
        """List stored fact rows matching the supplied filters."""
        statement = select(ClinicalFact)
        if person_id is not None:
            statement = statement.where(ClinicalFact.person_id == person_id)
        if person_ids is not None:
            if not person_ids:
                return []
            statement = statement.where(col(ClinicalFact.person_id).in_(person_ids))
        if fact_types:
            statement = statement.where(col(ClinicalFact.fact_type).in_(fact_types))
        statement = statement.order_by(
            col(ClinicalFact.effective_at).desc().nulls_last(),
            col(ClinicalFact.observed_at).desc().nulls_last(),
            col(ClinicalFact.id).desc(),
        )
        rows = list(self.session.exec(statement).all())
        if collapse_identities:
            rows = self._preferred_rows(rows)
        return rows[:limit] if limit is not None else rows

    def list_records(self, **filters: typing.Any) -> list[PersonClinicalRecord]:  # noqa: ANN401
        """List preferred fact assertions hydrated as typed domain records."""
        filters.setdefault("collapse_identities", True)
        return [hydrate_fact(row) for row in self.list_rows(**filters)]

    @staticmethod
    def _preferred_rows(rows: list[ClinicalFact]) -> list[ClinicalFact]:
        """Collapse repeated assertions while retaining every source in storage."""
        selected: dict[tuple[int, str, str], ClinicalFact] = {}
        for row in rows:
            key = (row.person_id, row.fact_type, row.identity_hash)
            current = selected.get(key)
            if current is None or ClinicalFactRepo._row_wins(current, row):
                selected[key] = row
        return [
            row
            for row in rows
            if selected[(row.person_id, row.fact_type, row.identity_hash)] is row
        ]

    @staticmethod
    def _row_wins(existing: ClinicalFact, candidate: ClinicalFact) -> bool:
        if existing.fact_type in {"weight", "lab"}:
            if (
                existing.extraction_method is ExtractionMethod.DETERMINISTIC
                and candidate.extraction_method is ExtractionMethod.AI
            ):
                return False
            if (
                existing.extraction_method is ExtractionMethod.AI
                and candidate.extraction_method is ExtractionMethod.DETERMINISTIC
            ):
                return True
        existing_time = ClinicalFactRepo._clinical_time(existing)
        candidate_time = ClinicalFactRepo._clinical_time(candidate)
        if candidate_time != existing_time:
            return candidate_time > existing_time
        return (candidate.id or -1) > (existing.id or -1)

    @staticmethod
    def _clinical_time(fact: ClinicalFact) -> datetime:
        value = fact.effective_at or fact.observed_at
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _incoming_wins(existing: ClinicalFact, incoming: ClinicalFact) -> bool:
        if existing.fact_type not in {"weight", "lab"}:
            return True
        return not (
            existing.extraction_method is ExtractionMethod.DETERMINISTIC
            and incoming.extraction_method is ExtractionMethod.AI
        )


__all__ = ["ClinicalFactRepo"]
