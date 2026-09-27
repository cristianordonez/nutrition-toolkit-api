"""Person-ingestion specialization of the shared extractor contract."""

from __future__ import annotations

from datetime import date  # noqa: TC003

from engine.models.extracted_fact_create import ExtractedFactCreate, PersonFactPayload
from engine.models.sql.clinical_source import SourceAuthority
from engine.pipelines.extraction import DocumentExtractor


class PersonExtractor(DocumentExtractor[list[ExtractedFactCreate]]):
    """Base class for deterministic person clinical document extractors."""

    async def extract_for_demo(self) -> list[ExtractedFactCreate]:
        """Extract transient facts, using normal identity rules by default."""
        return await self.extract()

    def _build_extracted_fact(  # noqa: PLR0913
        self,
        payload: PersonFactPayload,
        *,
        source_person_identifier: str | None = None,
        source_person_name: str | None = None,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
        source_page: int | None = None,
        source_system: str | None = None,
        source_record_type: str | None = None,
        source_authority: SourceAuthority = SourceAuthority.STRUCTURED_RECORD,
    ) -> ExtractedFactCreate:
        """Build one deterministic fact attributed to this extractor."""
        return ExtractedFactCreate(
            source_person_identifier=source_person_identifier,
            source_person_name=source_person_name,
            date_of_birth=date_of_birth,
            sex=sex,
            height_in=height_in,
            source_page=source_page,
            source_system=source_system,
            source_record_type=source_record_type,
            source_authority=source_authority,
            payload=payload,
            confidence=1.0,
            confidence_reason="Deterministic report extraction",
        )


__all__ = ["PersonExtractor"]
