from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.knowledge import KnowledgeChunkCreate, KnowledgeType
from ntk.models.sql.knowledge import Knowledge, KnowledgeChunk, KnowledgeChunkEmbedding
from ntk.models.sql.person import (
    ExtractionStatus,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
    Person,
    PersonClinicalNote,
    PersonNutritionClinicalNoteEmbedding,
)
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
from ntk.repositories.knowledge_repo import KnowledgeRepo
from ntk.utils.misc import require_id


def _person(session: Session) -> Person:
    person = Person(name="Person")
    session.add(person)
    session.commit()
    return person


def _generated_draft(person: Person, content: str) -> PersonClinicalNote:
    content_hash = sha256(" ".join(content.split()).encode()).hexdigest()
    return PersonClinicalNote(
        person_id=require_id(person.id),
        note_date=datetime.now(UTC),
        note_type=NutritionClinicalNoteType.NUTRITION_DIETARY.value,
        author="generation-model",
        note_text=content,
        raw_text=content,
        note_key=f"generated:{require_id(person.id)}:{content_hash}",
        extraction_status=ExtractionStatus.NOT_APPLICABLE,
        ncp_source=NutritionCareProcessSource.GENERATED,
        created_by="generation-model",
        ncp_index=0,
        content_hash=content_hash,
        status=NutritionCareProcessStatus.DRAFT,
    )


def test_clinical_note_repo_deduplicates_note_keys() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ClinicalNoteRepo(session)
        person = _person(session)
        first = _generated_draft(person, "Nutrition assessment")
        assert repository.create(first) is first
        duplicate = _generated_draft(person, "Nutrition assessment")
        assert repository.create(duplicate) is first


def test_generated_draft_is_deduplicated_by_content() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ClinicalNoteRepo(session)
        person = _person(session)
        existing = repository.create_generated_draft(
            _generated_draft(person, "Identical generated content"),
        )
        candidate = _generated_draft(person, "  Identical  generated content  ")
        assert repository.create_generated_draft(candidate) is existing
        assert len(session.exec(select(PersonClinicalNote)).all()) == 1


def test_finalize_and_embed_nutrition_clinical_note() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ClinicalNoteRepo(session)
        note = repository.create_generated_draft(
            _generated_draft(_person(session), "Nutrition assessment"),
        )
        finalized = repository.finalize_ncp(require_id(note.id))
        assert finalized is note
        assert finalized.status is NutritionCareProcessStatus.FINALIZED
        repository.update_ncp(
            note,
            embedding=[0.1],
            embedding_type=NutritionClinicalNoteType.NUTRITION_DIETARY,
            model_name="embedding-model",
        )
        embedding = session.exec(select(PersonNutritionClinicalNoteEmbedding)).one()
        assert embedding.person_clinical_note_id == note.id
        assert embedding.type is NutritionClinicalNoteType.NUTRITION_DIETARY


def test_list_ncps_excludes_regular_clinical_notes() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ClinicalNoteRepo(session)
        person = _person(session)
        ncp = repository.create_generated_draft(_generated_draft(person, "NCP"))
        repository.create(
            PersonClinicalNote(
                person_id=require_id(person.id),
                note_date=datetime.now(UTC),
                note_type="Nursing Note",
                note_text="Routine note",
                raw_text="Routine note",
                note_key="regular-note",
            ),
        )
        session.commit()
        assert repository.list_ncps() == [ncp]
        assert len(repository.list_clinical_notes()) == 2  # noqa: PLR2004


def test_knowledge_repo_stores_duplicate_chunks_under_separate_sources() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = KnowledgeRepo(session)
        for file_hash in ("first-file", "second-file"):
            repository.ingest(
                Knowledge(
                    filename=f"{file_hash}.pdf",
                    knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
                    file_hash=file_hash,
                ),
                [
                    KnowledgeChunkCreate(
                        content="Shared educational heading",
                        section_title="Education",
                        source_page_start=4,
                        source_page_end=4,
                    ),
                ],
                [[0.1]],
                "embedding-model",
            )
        knowledge = session.exec(select(Knowledge)).all()
        chunks = session.exec(select(KnowledgeChunk)).all()
        embeddings = session.exec(select(KnowledgeChunkEmbedding)).all()
    assert len(knowledge) == 2  # noqa: PLR2004
    assert len(chunks) == 2  # noqa: PLR2004
    assert len(embeddings) == 2  # noqa: PLR2004
    assert all(chunk.section_title == "Education" for chunk in chunks)
    assert all(chunk.source_page_start == 4 for chunk in chunks)  # noqa: PLR2004
