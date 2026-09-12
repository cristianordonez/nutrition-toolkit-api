from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.knowledge import KnowledgeChunkCreate, KnowledgeType
from ntk.models.sql.knowledge import (
    Knowledge,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
)
from ntk.models.sql.person import (
    AssessmentSource,
    Person,
    PersonAssessment,
    PersonAssessmentEmbedding,
    StatusType,
)
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.knowledge_repo import KnowledgeRepo
from ntk.utils.misc import require_id


def _assessment(
    person: Person,
    filename: str,
    content: str,
) -> PersonAssessment:
    return PersonAssessment(
        person_id=require_id(person.id),
        assessment_source=AssessmentSource.IMPORTED,
        source_filename=filename,
        created_by="dietitian",
        assessment_index=0,
        assessment_date=datetime.now(UTC).date(),
        content=content,
        content_hash=sha256(" ".join(content.split()).encode()).hexdigest(),
    )


def _person(session: Session) -> Person:
    person = Person(name="Person")
    session.add(person)
    session.commit()
    return person


def test_assessment_repo_deduplicates_content_across_sources() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = AssessmentRepo(session)
        person = _person(session)
        first = _assessment(
            person,
            "first-file.pdf",
            "Nutrition assessment\nwith plan",
        )
        repository.ingest(
            [first],
            [[0.1]],
            "embedding-model",
        )
        assert repository.get_by_id(require_id(first.id)) is first
        second = _assessment(
            person,
            "second-file.pdf",
            " Nutrition assessment with plan ",
        )
        repository.ingest(
            [second],
            [[0.2]],
            "embedding-model",
        )

        assessments = session.exec(select(PersonAssessment)).all()
        embeddings = session.exec(select(PersonAssessmentEmbedding)).all()

    assert len(assessments) == 1
    assert len(embeddings) == 1
    assert assessments[0].assessment_source is AssessmentSource.IMPORTED
    assert assessments[0].source_filename == "first-file.pdf"
    assert assessments[0].created_by == "dietitian"


def test_assessment_repo_finalizes_assessment() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = AssessmentRepo(session)
        assessment = _assessment(
            _person(session),
            "assessment.pdf",
            "Nutrition assessment",
        )
        session.add(assessment)
        session.commit()

        result = repository.finalize(require_id(assessment.id))

        assert result is assessment
        assert result.status is StatusType.FINALIZED
        assert result.finalized_at is not None

        finalized_at = result.finalized_at
        repeated_result = repository.finalize(require_id(assessment.id))
        assert repeated_result is not None
        assert repeated_result.finalized_at == finalized_at


def test_assessment_repo_overwrites_by_source_filename() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = AssessmentRepo(session)
        person = _person(session)
        source = _assessment(person, "same-file.pdf", "Original assessment")
        repository.ingest(
            [source],
            [[0.1]],
            "embedding-model",
        )
        replacement = _assessment(
            person,
            "same-file.pdf",
            "Replacement assessment",
        )
        replacement.assessment_index = 1
        replacement.created_by = "consultant"
        repository.ingest(
            [replacement],
            [[0.2]],
            "embedding-model",
            overwrite=True,
        )

        assessments = session.exec(select(PersonAssessment)).all()
        embeddings = session.exec(select(PersonAssessmentEmbedding)).all()
        count = repository.count_assessments("same-file.pdf")

    assert len(assessments) == 1
    assert len(embeddings) == 1
    assert count == 1
    assert assessments[0].content == "Replacement assessment"
    assert assessments[0].assessment_index == 1
    assert assessments[0].created_by == "consultant"


def test_knowledge_repo_stores_duplicate_chunks_under_separate_sources() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = KnowledgeRepo(session)
        for file_hash in ("first-file", "second-file"):
            knowledge_source = Knowledge(
                filename=f"{file_hash}.pdf",
                knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
                file_hash=file_hash,
            )
            repository.ingest(
                knowledge_source,
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
