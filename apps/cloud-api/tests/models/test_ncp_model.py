from __future__ import annotations

from sqlmodel import SQLModel

from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessEmbedding,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
)


def test_ncp_and_embedding_link_directly() -> None:
    ncp = NutritionCareProcess(
        id=1,
        person_identifier="person-1",
        facility_identifier="facility-1",
        note_text="Nutrition assessment",
        content_hash="content-hash",
        created_by="dietitian",
        ncp_source=NutritionCareProcessSource.IMPORTED,
        source_filename="assessment.pdf",
        status=NutritionCareProcessStatus.FINALIZED,
    )
    embedding = NutritionCareProcessEmbedding(
        nutrition_care_process_id=1,
        embedding_vector=[0.1, 0.2],
        type=NutritionClinicalNoteType.NUTRITION_DIETARY,
        model_name="text-embedding-3-small",
        nutrition_care_process=ncp,
    )

    assert ncp.ncp_source is NutritionCareProcessSource.IMPORTED
    assert ncp.source_filename == "assessment.pdf"
    assert ncp.created_by == "dietitian"
    assert embedding.nutrition_care_process_id == ncp.id
    assert embedding.nutrition_care_process is ncp
    assert ncp.nutrition_embeddings == [embedding]
    assert "created_by" in NutritionCareProcess.__table__.c  # ty: ignore[unresolved-attribute]
    assert "person_clinical_note" not in SQLModel.metadata.tables
    foreign_key = next(
        iter(
            NutritionCareProcessEmbedding.__table__.c.nutrition_care_process_id.foreign_keys,  # ty: ignore[unresolved-attribute]
        ),
    )
    assert foreign_key.target_fullname == "nutrition_care_process.id"


def test_ncp_sources_are_generated_or_imported() -> None:
    assert list(NutritionCareProcessSource) == [
        NutritionCareProcessSource.GENERATED,
        NutritionCareProcessSource.IMPORTED,
    ]
