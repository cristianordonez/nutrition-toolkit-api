from __future__ import annotations

from hashlib import sha256

from sqlmodel import Session, SQLModel, create_engine, select

from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessEmbedding,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
)
from api.repositories.ncp_repo import NCPRepo


def _generated_draft(content: str) -> NutritionCareProcess:
    content_hash = sha256(" ".join(content.split()).encode()).hexdigest()
    return NutritionCareProcess(
        person_identifier="R1",
        note_text=content,
        content_hash=content_hash,
        created_by="generation-model",
        ncp_source=NutritionCareProcessSource.GENERATED,
        status=NutritionCareProcessStatus.DRAFT,
    )


def test_create_generated_draft_deduplicates_by_content() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = NCPRepo(session)
        existing = repository.create_generated_draft(
            _generated_draft("Identical generated content"),
        )
        candidate = _generated_draft("  Identical  generated content  ")
        assert repository.create_generated_draft(candidate) is existing
        assert len(session.exec(select(NutritionCareProcess)).all()) == 1


def test_create_generated_draft_rejects_non_draft_ncps() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = NCPRepo(session)
        ncp = _generated_draft("Finalized content")
        ncp.status = NutritionCareProcessStatus.FINALIZED

        try:
            repository.create_generated_draft(ncp)
        except ValueError as error:
            assert "draft regeneration" in str(error)
        else:
            message = "expected ValueError"
            raise AssertionError(message)


def test_finalize_and_embed_ncp() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = NCPRepo(session)
        ncp = repository.create_generated_draft(_generated_draft("Nutrition assessment"))
        finalized = repository.finalize_ncp(ncp.id, "R1")
        assert finalized is ncp
        assert finalized.status is NutritionCareProcessStatus.FINALIZED
        repository.update_ncp(
            ncp,
            embedding=[0.1],
            embedding_type=NutritionClinicalNoteType.NUTRITION_DIETARY,
            model_name="embedding-model",
        )
        embedding = session.exec(select(NutritionCareProcessEmbedding)).one()
        assert embedding.nutrition_care_process_id == ncp.id
        assert embedding.type is NutritionClinicalNoteType.NUTRITION_DIETARY


def test_finalize_ncp_is_scoped_to_the_owning_person() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = NCPRepo(session)
        ncp = repository.create_generated_draft(_generated_draft("Nutrition assessment"))

        assert repository.finalize_ncp(ncp.id, "someone-else") is None


def test_list_ncps_orders_newest_first() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = NCPRepo(session)
        first = repository.create_generated_draft(_generated_draft("First"))
        second = repository.create_generated_draft(_generated_draft("Second"))

        assert repository.list_ncps("R1") == [second, first]


def test_count_ncps_counts_imported_records_for_one_source_file() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = NCPRepo(session)
        imported = _generated_draft("Imported content")
        imported.ncp_source = NutritionCareProcessSource.IMPORTED
        imported.source_filename = "report.pdf"
        repository.save_ncp(imported)
        repository.save_ncp(_generated_draft("Generated content"))

        assert repository.count_ncps("report.pdf") == 1
