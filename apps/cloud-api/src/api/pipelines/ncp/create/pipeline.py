"""Multistep workflows for generating and maintaining Nutrition Care Processes."""

from __future__ import annotations

import logging
import typing
from datetime import UTC, datetime
from hashlib import sha256

from api.agents.ncp_agent import NCP_MODEL, NutritionCareProcessAgent
from api.models.ncp_context import BudgetedNCPContext
from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
)
from api.services.embedding_service import EmbeddingService
from ntk.utils.tokens import truncate_to_tokens

if typing.TYPE_CHECKING:
    from api.models.rag import RagSearchMatch
    from api.repositories.embedding_repo import EmbeddingRepo
    from api.repositories.ncp_repo import NCPRepo
    from ntk.models.ncp_context import NCPGenerationRequest


_NCP_MATCH_LIMIT = 5
_NCP_CHUNK_TOKENS = 1_200
logger = logging.getLogger(__name__)


class FinalizedNCPError(ValueError):
    """Raised when an update would mutate a finalized NCP."""


class NutritionCareProcessPipeline:
    """Coordinate NCP workflows through shared repository dependencies."""

    def __init__(
        self,
        ncp_repository: NCPRepo,
        *,
        embedding_repository: EmbeddingRepo | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Store workflow dependencies and lazily create vector infrastructure."""
        self.embedding_repository = embedding_repository
        self.ncp_repository = ncp_repository
        self.embedding_service = embedding_service

    async def generate(
        self,
        request: NCPGenerationRequest,
    ) -> NutritionCareProcess:
        """Look up relevant past NCPs, generate, and persist a draft NCP."""
        relevant_ncps = await self._search_relevant_ncps(
            request.summary_text,
            request.person_identifier,
        )
        context = BudgetedNCPContext(
            person=request.person,
            relevant_ncps=relevant_ncps,
            additional_context=request.additional_context,
        )
        content = await NutritionCareProcessAgent(
            embedding_service=self._embedding_service(),
        ).run(context)
        content_hash = self._content_hash(content)
        ncp = NutritionCareProcess(
            person_identifier=request.person_identifier,
            facility_identifier=request.facility_identifier,
            note_text=content,
            content_hash=content_hash,
            created_by=NCP_MODEL,
            ncp_source=NutritionCareProcessSource.GENERATED,
            status=NutritionCareProcessStatus.DRAFT,
            model_name=NCP_MODEL,
        )
        return self.ncp_repository.create_generated_draft(ncp)

    async def _search_relevant_ncps(
        self,
        summary_text: str,
        person_identifier: str,
    ) -> list[RagSearchMatch]:
        """Retrieve and bound similar past NCPs for one person."""
        matches = await self._embedding_service().search_ncps_async(
            summary_text,
            person_identifier,
            top_k=_NCP_MATCH_LIMIT,
        )
        return [
            match.model_copy(
                update={
                    "chunk_text": truncate_to_tokens(
                        match.chunk_text,
                        _NCP_CHUNK_TOKENS,
                    ),
                },
            )
            for match in matches[:_NCP_MATCH_LIMIT]
        ]

    async def finalize(
        self,
        ncp_id: int,
        person_identifier: str,
    ) -> NutritionCareProcess | None:
        """Finalize an NCP and ensure its retrieval embedding exists."""
        ncp = self.ncp_repository.finalize_ncp(ncp_id, person_identifier)
        if ncp is not None:
            await self.embed_ncp(ncp)
        return ncp

    async def update(
        self,
        ncp_id: int,
        person_identifier: str,
        *,
        note_text: str | None = None,
        created_by: str | None = None,
        status: NutritionCareProcessStatus | None = None,
    ) -> NutritionCareProcess | None:
        """Apply edits to a draft NCP and optionally finalize it."""
        ncp = self.ncp_repository.get_ncp(ncp_id, person_identifier)
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
            created_by=created_by,
            status=status,
        )
        embedding: list[float] | None = None
        embedding_model: str | None = None
        if content_changed and ncp.status is NutritionCareProcessStatus.FINALIZED:
            vector_service = self._embedding_service()
            embedding = await vector_service.get_embedding_async(ncp.note_text)
            embedding_model = vector_service.embedding_model
        updated = self.ncp_repository.update_ncp(
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
        ncp: NutritionCareProcess,
        *,
        note_text: str | None,
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

    async def embed_ncp(self, ncp: NutritionCareProcess) -> bool:
        """Create a missing embedding for a finalized NCP."""
        embedding_type = self.nutrition_note_type(ncp)
        if (
            ncp.status is not NutritionCareProcessStatus.FINALIZED
            or embedding_type is None
        ):
            return False
        if ncp.id is None:
            return False
        if self.ncp_repository.get_embedding(ncp.id) is not None:
            return False
        vector_service = self._embedding_service()
        embedding = await vector_service.get_embedding_async(ncp.note_text)
        self.ncp_repository.update_ncp(
            ncp,
            embedding=embedding,
            embedding_type=embedding_type,
            model_name=vector_service.embedding_model,
        )
        return True

    async def sync_ncps(self) -> typing.NoReturn:
        """Promote imported clinical notes into searchable NCPs.

        Deferred: this promotion has no coherent home now that NCP generation
        and storage live behind cloud-api's stateless HTTP boundary while
        clinical notes are extracted and stored entirely on-device. Redesign
        this once device<->cloud sync for imported notes is decided (see the
        split refactor plan, decision 7). Local clinical-note ingestion
        (``engine.pipelines.ncp.ingest.import_pipeline``) still works; only
        this promotion step is unimplemented.
        """
        msg = (
            "NCP import/promotion is deferred pending a device<->cloud sync "
            "redesign -- see the split refactor plan (decision 7)"
        )
        raise NotImplementedError(msg)

    @staticmethod
    def nutrition_note_type(
        ncp: NutritionCareProcess,
    ) -> NutritionClinicalNoteType | None:
        """Return the canonical embedding type for a generated NCP.

        Every row in this table is a generated NCP until the deferred
        import/promotion feature (decision 7) distinguishes dietician-authored
        notes again, so this always classifies as nutrition/dietary today.
        """
        del ncp
        return NutritionClinicalNoteType.NUTRITION_DIETARY

    @staticmethod
    def _content_hash(content: str) -> str:
        return sha256(" ".join(content.split()).encode()).hexdigest()

    def _embedding_service(self) -> EmbeddingService:
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService(self.embedding_repository)
        return self.embedding_service


__all__ = ["FinalizedNCPError", "NutritionCareProcessPipeline"]
