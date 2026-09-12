from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REVISIONS = [
    "20260912_0001",
]


def _config(database_url: str | None = None) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    if database_url is not None:
        config.attributes["connection_url"] = database_url
    return config


def test_revision_history_is_linear_and_has_one_head() -> None:
    scripts = ScriptDirectory.from_config(_config())

    assert scripts.get_heads() == [EXPECTED_REVISIONS[-1]]
    assert [revision.revision for revision in scripts.walk_revisions()][::-1] == (
        EXPECTED_REVISIONS
    )


def test_offline_upgrade_renders_singleton_diet_constraint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    command.upgrade(_config(), "head", sql=True)

    sql = capsys.readouterr().out
    assert "DROP CONSTRAINT person_diet_person_id_state_key_key" in sql
    assert "ADD CONSTRAINT person_diet_person_id_key UNIQUE (person_id)" in sql


@pytest.mark.skipif(
    "NTK_ALEMBIC_TEST_DATABASE_URL" not in os.environ,
    reason="set NTK_ALEMBIC_TEST_DATABASE_URL to an empty disposable PostgreSQL DB",
)
def test_postgresql_upgrade_enforces_one_diet_per_person() -> None:
    """Exercise the diet constraint migration against disposable PostgreSQL."""
    database_url = os.environ["NTK_ALEMBIC_TEST_DATABASE_URL"]
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    existing_tables = set(inspector.get_table_names())
    assert not existing_tables, (
        "NTK_ALEMBIC_TEST_DATABASE_URL must reference an empty disposable database; "
        f"found {sorted(existing_tables)}"
    )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                CREATE TABLE person_diet (
                    id SERIAL PRIMARY KEY,
                    person_id INTEGER NOT NULL,
                    state_key VARCHAR NOT NULL,
                    CONSTRAINT person_diet_person_id_state_key_key
                        UNIQUE (person_id, state_key)
                )
                """,
            ),
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO person_diet (person_id, state_key)
                VALUES (7, 'regular')
                """,
            ),
        )

    config = _config(database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    with engine.connect() as connection:
        constraints = sa.inspect(connection).get_unique_constraints("person_diet")
        assert any(
            constraint["column_names"] == ["person_id"] for constraint in constraints
        )
