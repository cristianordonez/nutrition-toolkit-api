"""Ollama is no longer a provider; a stored choice becomes Local AI.

Revision ID: 0004
Revises: 0003

Both keep data on the device, so this never moves anyone to a hosted model.
"""

from __future__ import annotations

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Move a stored ``ollama`` selection to ``local``."""
    op.execute("UPDATE settings SET ai_provider = 'local' WHERE ai_provider = 'ollama'")


def downgrade() -> None:
    """Nothing to restore: which rows were ``ollama`` is not recorded."""
