from __future__ import annotations

from engine.controllers.knowledge.ingest import KnowledgeIngestResponse
from engine.models.sql.knowledge import Knowledge, KnowledgeChunk, KnowledgeType


def test_knowledge_ingest_response_renders_created_chunk_count() -> None:
    response = KnowledgeIngestResponse(
        documents=[
            Knowledge(
                filename="diet-manual.pdf",
                knowledge_type=KnowledgeType.DIET_MANUAL,
                file_hash="diet-manual",
                chunks=[
                    KnowledgeChunk(
                        knowledge_id=1,
                        chunk_index=index,
                        content=f"Chunk {index}",
                    )
                    for index in range(3)
                ],
            ),
            Knowledge(
                filename="nutrition-care-manual.pdf",
                knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
                file_hash="nutrition-care-manual",
                chunks=[
                    KnowledgeChunk(
                        knowledge_id=2,
                        chunk_index=0,
                        content="Chunk 0",
                    ),
                ],
            ),
        ],
    )

    assert response.to_console() == (
        "# diet-manual.pdf\n# nutrition-care-manual.pdf\nCreated 4 chunk(s)."
    )
