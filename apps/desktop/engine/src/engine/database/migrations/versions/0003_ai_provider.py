"""Replace the cloud on/off switch with an explicit AI provider choice.

Revision ID: 0003
Revises: 0002

``use_cloud_model`` could only say "hosted or not". The provider is now one of
``local`` (the app's own llama.cpp runtime), ``ollama`` (a user-run Ollama)
or ``openai``. A user who had switched the cloud on keeps ``openai``; everyone
else starts on ``local``, which keeps data on the device as before.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

_PROVIDER = sa.Enum("local", "ollama", "openai", name="ai_provider")


def _settings(*columns: sa.Column) -> sa.Table:
    """Freeze the settings table so batch mode need not reflect it.

    Reflection needs a live database; a frozen definition also lets
    ``alembic upgrade --sql`` render this revision offline.
    """
    return sa.Table(
        "settings",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("credentials", sa.String(), nullable=True),
        sa.Column("dark_mode", sa.Boolean(), nullable=True),
        *columns,
        sa.CheckConstraint("id = 1", name="ck_settings_singleton"),
    )


def _cloud_switch() -> sa.Column:
    return sa.Column("use_cloud_model", sa.Boolean(), nullable=False)


def _provider() -> sa.Column:
    return sa.Column("ai_provider", _PROVIDER, nullable=False, server_default="local")


def upgrade() -> None:
    """Add ``ai_provider``, carry the old switch over, then drop it."""
    with op.batch_alter_table(
        "settings",
        copy_from=_settings(_cloud_switch()),
    ) as batch:
        batch.add_column(
            sa.Column(
                "ai_provider",
                _PROVIDER,
                nullable=False,
                server_default="local",
            ),
        )
    op.execute(
        "UPDATE settings SET ai_provider = CASE WHEN use_cloud_model "
        "THEN 'openai' ELSE 'local' END",
    )
    with op.batch_alter_table(
        "settings",
        copy_from=_settings(_cloud_switch(), _provider()),
    ) as batch:
        batch.drop_column("use_cloud_model")


def downgrade() -> None:
    """Restore the switch; only ``openai`` maps back to "cloud on"."""
    with op.batch_alter_table("settings", copy_from=_settings(_provider())) as batch:
        batch.add_column(
            sa.Column(
                "use_cloud_model",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    op.execute(
        "UPDATE settings SET use_cloud_model = (ai_provider = 'openai')",
    )
    with op.batch_alter_table(
        "settings",
        copy_from=_settings(_provider(), _cloud_switch()),
    ) as batch:
        batch.drop_column("ai_provider")
