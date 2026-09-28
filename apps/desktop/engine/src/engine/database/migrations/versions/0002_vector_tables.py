"""Store knowledge and NCP vectors directly in sqlite-vec virtual tables.

Revision ID: 0002
Revises: 0001

The width is frozen for all-MiniLM-L6-v2. Future model changes need a new
revision and re-embedding; historical migrations must not import live model
constants. vec0 owns the vectors and its internal shadow tables.
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create cosine vector storage and invalidate vectors with their sources."""
    op.execute(
        """
        CREATE VIRTUAL TABLE knowledge_chunk_vector USING vec0(
            knowledge_chunk_id INTEGER PRIMARY KEY,
            embedding FLOAT[384] distance_metric=cosine,
            model TEXT
        )
        """,
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE ncp_note_vector USING vec0(
            ncp_note_id INTEGER PRIMARY KEY,
            embedding FLOAT[384] distance_metric=cosine,
            model TEXT
        )
        """,
    )
    # Virtual tables cannot declare foreign keys. Triggers on the relational
    # parents handle deletes (including cascades) and changed source content.
    for source, vector, key in (
        ("knowledge_chunk", "knowledge_chunk_vector", "knowledge_chunk_id"),
        ("ncp_note", "ncp_note_vector", "ncp_note_id"),
    ):
        op.execute(
            f"""
            CREATE TRIGGER {source}_delete_vector AFTER DELETE ON {source}
            BEGIN
                DELETE FROM {vector} WHERE {key} = OLD.id;
            END
            """,  # noqa: S608 - identifiers are migration literals
        )
        op.execute(
            f"""
            CREATE TRIGGER {source}_invalidate_vector
            AFTER UPDATE OF content ON {source}
            WHEN OLD.content IS NOT NEW.content
            BEGIN
                DELETE FROM {vector} WHERE {key} = OLD.id;
            END
            """,  # noqa: S608 - identifiers are migration literals
        )


def downgrade() -> None:
    """Drop vector storage; source notes and knowledge chunks remain intact."""
    for source in ("ncp_note", "knowledge_chunk"):
        op.execute(f"DROP TRIGGER {source}_invalidate_vector")
        op.execute(f"DROP TRIGGER {source}_delete_vector")
    op.execute("DROP TABLE ncp_note_vector")
    op.execute("DROP TABLE knowledge_chunk_vector")
