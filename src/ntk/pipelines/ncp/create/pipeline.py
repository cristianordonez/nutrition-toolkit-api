"""Multistep workflows for generating and maintaining Nutrition Care Processes."""

from __future__ import annotations

import asyncio
import logging
import typing
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, PrivateAttr

from ntk.agents.ncp_agent import NCP_MODEL, NutritionCareProcessAgent
from ntk.models.sql.person import (
    ExtractionStatus,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
    Person,
    PersonClinicalNote,
)
from ntk.pipelines.ncp.create.context_budgeter import (
    ContextBudgeter,
    ContextBudgetResult,
)
from ntk.services.embedding_service import EmbeddingService
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from ntk.models.person_detail import PersonDetail
    from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
    from ntk.repositories.embedding_repo import EmbeddingRepo
    from ntk.repositories.food_repo import FoodRepo
    from ntk.services.person.person_service import PersonService


_NCP_MATCH_LIMIT = 5
logger = logging.getLogger(__name__)


class FinalizedNCPError(ValueError):
    """Raised when an update would mutate a finalized NCP."""


class NCPGenerationRequest(typing.Protocol):
    """Person-specific input accepted by batch ncp generation."""

    source_person_identifier: str
    source_system: str
    facility_identifier: str | None
    context: str | None


class NCPSyncResult(BaseModel):
    """Summary of one historical NCP synchronization run."""

    scanned: int = 0
    ncps_created: int = 0
    ncps_existing: int = 0
    embeddings_created: int = 0
    embeddings_existing: int = 0
    skipped_not_nutrition: int = 0
    failed: int = 0
    _created_ncps: list[PersonClinicalNote] = PrivateAttr(default_factory=list)

    @property
    def created_ncps(self) -> list[PersonClinicalNote]:
        """Return NCPs created during this run for internal callers."""
        return self._created_ncps


class NutritionCareProcessPipeline:
    """Coordinate NCP workflows through shared repository dependencies."""

    def __init__(  # noqa: PLR0913
        self,
        clinical_note_repository: ClinicalNoteRepo,
        *,
        person_service: PersonService | None = None,
        embedding_repository: EmbeddingRepo | None = None,
        food_repository: FoodRepo | None = None,
        embedding_service: EmbeddingService | None = None,
        context_budgeter: ContextBudgeter | None = None,
    ) -> None:
        """Store workflow dependencies and lazily create vector infrastructure."""
        self.person_service = person_service
        self.embedding_repository = embedding_repository
        self.food_repository = food_repository
        self.clinical_note_repository = clinical_note_repository
        self.embedding_service = embedding_service
        self.context_budgeter = context_budgeter or ContextBudgeter()

    async def generate(
        self,
        source_person_identifier: str,
        *,
        facility_identifier: str | None = None,
        context: str | None = None,
    ) -> PersonClinicalNote:
        """Resolve a person, retrieve context, and persist a draft NCP."""
        person_detail = self._person_service().get_person_detail(
            source_person_identifier,
            facility_identifier=facility_identifier,
        )
        person_id = require_id(person_detail.person_id)
        person = self._person_service().repository.get_by_id(person_id)
        if person is None:
            msg = f"Person {person_id} was not found"
            raise LookupError(msg)
        return await self.generate_for_person(
            person,
            person_detail,
            context=context,
        )

    async def generate_for_person(
        self,
        person: Person,
        person_detail: PersonDetail,
        *,
        context: str | None = None,
        budgeted_context: ContextBudgetResult | None = None,
    ) -> PersonClinicalNote:
        """Generate and persist an NCP from prepared person details."""
        person_id = require_id(person.id)
        if person_detail.person_id != person_id:
            msg = "Person detail does not belong to the supplied person"
            raise ValueError(msg)
        budgeted = budgeted_context or await self.prepare_context(
            person_detail,
            additional_context=context,
        )
        content = await NutritionCareProcessAgent(
            food_repo=self._food_repository(),
            embedding_service=self._embedding_service(),
        ).run(budgeted.ncp_context)
        ncp = PersonClinicalNote(
            person_id=person_id,
            person=person,
            note_date=datetime.now(UTC),
            note_type=NutritionClinicalNoteType.NUTRITION_DIETARY.value,
            author=NCP_MODEL,
            note_text=content,
            raw_text=content,
            note_key=f"generated-ncp:{person_id}:{self._content_hash(content)}",
            extraction_status=ExtractionStatus.NOT_APPLICABLE,
            ncp_source=NutritionCareProcessSource.GENERATED,
            content_hash=self._content_hash(content),
            ncp_index=0,
            created_by=NCP_MODEL,
            status=NutritionCareProcessStatus.DRAFT,
            model_name=NCP_MODEL,
        )
        return self.clinical_note_repository.create_generated_draft(ncp)

    async def prepare_context(
        self,
        person_detail: PersonDetail,
        *,
        additional_context: str | None = None,
    ) -> ContextBudgetResult:
        """Retrieve similar NCPs and build the bounded agent context."""
        summary = person_detail.create_summary_text()
        relevant_ncps = await asyncio.to_thread(
            self._embedding_service().search_ncps,
            summary,
            top_k=_NCP_MATCH_LIMIT,
        )
        return self.context_budgeter.budget(
            person_detail,
            relevant_ncps=relevant_ncps,
            additional_context=additional_context,
        )

    async def generate_many(
        self,
        requests: typing.Sequence[NCPGenerationRequest],
    ) -> list[PersonClinicalNote]:
        """Generate NCPs once per unique facility/person pair."""
        ncps: list[PersonClinicalNote] = []
        seen: set[tuple[str | None, str]] = set()
        for request in requests:
            person_key = (
                request.facility_identifier,
                request.source_person_identifier,
            )
            if person_key in seen:
                continue
            seen.add(person_key)
            ncps.append(
                await self.generate(
                    request.source_person_identifier,
                    facility_identifier=request.facility_identifier,
                    context=request.context,
                ),
            )
        return ncps

    async def finalize(self, ncp_id: int) -> PersonClinicalNote | None:
        """Finalize an NCP and ensure its retrieval embedding exists."""
        ncp = self.clinical_note_repository.finalize_ncp(ncp_id)
        if ncp is not None:
            await self.embed_ncp(ncp)
        return ncp

    async def update(
        self,
        ncp_id: int,
        *,
        note_text: str | None = None,
        note_date: datetime | None = None,
        created_by: str | None = None,
        status: NutritionCareProcessStatus | None = None,
    ) -> PersonClinicalNote | None:
        """Apply edits to a draft NCP and optionally finalize it."""
        ncp = self.clinical_note_repository.get_ncp(ncp_id)
        if ncp is None:
            return None
        if ncp.status is NutritionCareProcessStatus.FINALIZED:
            message = (
                f"Nutrition Care Process {ncp_id} is finalized and cannot be edited"
            )
            raise FinalizedNCPError(message)
        content_changed = self._apply_updates(
            ncp,
            note_text=note_text,
            note_date=note_date,
            created_by=created_by,
            status=status,
        )
        embedding: list[float] | None = None
        embedding_model: str | None = None
        if content_changed and ncp.status is NutritionCareProcessStatus.FINALIZED:
            vector_service = self._embedding_service()
            embedding = await vector_service.get_embedding_async(ncp.note_text)
            embedding_model = vector_service.embedding_model
        updated = self.clinical_note_repository.update_ncp(
            ncp,
            embedding=embedding,
            embedding_type=(
                self.nutrition_note_type(ncp) if embedding is not None else None
            ),
            model_name=embedding_model,
        )
        if updated.status is NutritionCareProcessStatus.FINALIZED and embedding is None:
            await self.embed_ncp(updated)
        return updated

    @staticmethod
    def _apply_updates(
        ncp: PersonClinicalNote,
        *,
        note_text: str | None,
        note_date: datetime | None,
        created_by: str | None,
        status: NutritionCareProcessStatus | None,
    ) -> bool:
        """Mutate supplied NCP fields and report whether content changed."""
        if note_text is not None:
            normalized_content = " ".join(note_text.split())
            if not normalized_content:
                message = "Nutrition Care Process content cannot be empty"
                raise ValueError(message)
            ncp.note_text = note_text.strip()
            ncp.content_hash = NutritionCareProcessPipeline._content_hash(note_text)
        if note_date is not None:
            ncp.note_date = note_date
        if created_by is not None:
            normalized_creator = created_by.strip()
            if not normalized_creator:
                message = "Nutrition Care Process creator cannot be empty"
                raise ValueError(message)
            ncp.created_by = normalized_creator
        if status is not None:
            ncp.status = status
            if (
                status is NutritionCareProcessStatus.FINALIZED
                and ncp.finalized_at is None
            ):
                ncp.finalized_at = datetime.now(UTC)
            elif status is NutritionCareProcessStatus.DRAFT:
                ncp.finalized_at = None
        return note_text is not None

    async def embed_ncp(self, ncp: PersonClinicalNote) -> bool:
        """Create a missing embedding for a finalized NCP."""
        embedding_type = self.nutrition_note_type(ncp)
        if (
            ncp.status is not NutritionCareProcessStatus.FINALIZED
            or embedding_type is None
        ):
            return False
        ncp_id = require_id(ncp.id)
        if self.clinical_note_repository.get_embedding(ncp_id) is not None:
            return False
        vector_service = self._embedding_service()
        embedding = await vector_service.get_embedding_async(ncp.note_text)
        self.clinical_note_repository.update_ncp(
            ncp,
            embedding=embedding,
            embedding_type=embedding_type,
            model_name=vector_service.embedding_model,
        )
        return True

    async def sync_ncps(self) -> NCPSyncResult:
        """Create imported NCPs and embeddings from eligible notes."""
        result = NCPSyncResult()
        for note in self.clinical_note_repository.list_clinical_notes():
            result.scanned += 1
            if self.nutrition_note_type(note) is None:
                result.skipped_not_nutrition += 1
                continue
            try:
                if note.ncp_source is None:
                    ncp = self.clinical_note_repository.save_ncp(
                        self._promote_to_ncp(note),
                    )
                    result.ncps_created += 1
                    result.created_ncps.append(ncp)
                else:
                    ncp = note
                    result.ncps_existing += 1
                if ncp.status is not NutritionCareProcessStatus.FINALIZED:
                    continue
                if await self.embed_ncp(ncp):
                    result.embeddings_created += 1
                else:
                    result.embeddings_existing += 1
            except Exception:
                result.failed += 1
                logger.exception("Failed to synchronize clinical note %s", note.id)
        return result

    async def sync(self) -> NCPSyncResult:
        """Run the historical NCP synchronization workflow."""
        return await self.sync_ncps()

    @staticmethod
    def nutrition_note_type(
        note: PersonClinicalNote,
    ) -> NutritionClinicalNoteType | None:
        """Return the canonical embedding type for an eligible note label."""
        note_type = " ".join((note.note_type or "").casefold().split())
        if note_type in {"nutrition/dietary", "nutrition/dietary note"}:
            return NutritionClinicalNoteType.NUTRITION_DIETARY
        if note_type in {"dietician", "dietitian"} or note_type.startswith(
            ("dietician ", "dietitian "),
        ):
            return NutritionClinicalNoteType.DIETICIAN
        return None

    @staticmethod
    def _promote_to_ncp(note: PersonClinicalNote) -> PersonClinicalNote:
        content = note.note_text
        if not content.strip():
            msg = f"Clinical note {note.id} has no Nutrition Care Process text"
            raise ValueError(msg)
        creator = (note.author or "").strip() or "unknown"
        note.ncp_source = NutritionCareProcessSource.IMPORTED
        note.content_hash = NutritionCareProcessPipeline._content_hash(content)
        note.ncp_index = 0
        note.created_by = creator
        note.status = NutritionCareProcessStatus.FINALIZED
        note.finalized_at = note.note_date
        return note

    @staticmethod
    def _content_hash(content: str) -> str:
        return sha256(" ".join(content.split()).encode()).hexdigest()

    def _person_service(self) -> PersonService:
        if self.person_service is None:
            msg = "A person service is required for NCP generation"
            raise RuntimeError(msg)
        return self.person_service

    def _food_repository(self) -> FoodRepo:
        if self.food_repository is None:
            msg = "A food repository is required for NCP generation"
            raise RuntimeError(msg)
        return self.food_repository

    def _embedding_service(self) -> EmbeddingService:
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService(self.embedding_repository)
        return self.embedding_service


__all__ = [
    "NCPGenerationRequest",
    "NCPSyncResult",
    "NutritionCareProcessPipeline",
]
