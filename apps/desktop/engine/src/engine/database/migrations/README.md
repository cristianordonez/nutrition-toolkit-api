# Desktop database migrations

`engine.database.bootstrap.initialize_database()` upgrades the configured SQLite
database to Alembic `head`, then seeds the formula catalog and singleton settings.
The CLI calls it before running commands. `db.py` configures connections and loads
sqlite-vec; `sessions.py` owns shared session boundaries.

Migrations, including this environment, are packaged inside `engine`. Runtime
bootstrap constructs an Alembic `Config` in Python and does not read an ini file
or depend on the current working directory.

## Development commands

From the repository root, use the root `alembic.ini`. The package also has an ini
for running the same commands from `apps/desktop/engine`.

```sh
export NTK_DATABASE_PATH=/absolute/path/to/development-facts.db
uv run --package engine alembic upgrade head
uv run --package engine alembic current
uv run --package engine alembic check
uv run --package engine alembic revision --autogenerate -m "describe schema change"
```

Review generated revisions before applying them. SQLite table alterations use
Alembic batch mode. Revisions must freeze their schema and must not import live
application models or call `metadata.create_all()`. SQLModel `AutoString` types
are rendered as SQLAlchemy `String` so generated files are self-contained.

The disconnected Postgres server has its own `apps/server/alembic.ini` and
revision history. Always select that config or work from `apps/server` when
migrating the server.

## Initial history and existing development databases

- `0001` creates the relational tables, indexes, and constraints.
- `0002` creates `knowledge_chunk_vector` and `ncp_note_vector` using sqlite-vec
  `vec0`, with 384-element float32 cosine vectors for `all-MiniLM-L6-v2`.

This initial history targets a fresh SQLite database. Databases previously
created by `create_all()` have no Alembic version; bootstrap refuses them before
changing tables. Keep the old file and select a new `NTK_DATABASE_PATH`, or plan
an explicit data migration from a backup. Do not stamp an unverified legacy
database or delete it automatically.

Alembic runs inside `BEGIN IMMEDIATE`, including its version check, so parallel
CLI processes serialize startup and failed migrations roll back their DDL.

## Vector schema

The vector tables are the only storage for embeddings. Their integer primary
keys match `knowledge_chunk.id` and `ncp_note.id`. Each row retains the model name;
queries filter by model and eligible source IDs inside the KNN search before
applying `k`. Vectors must have the fixed width and be finite and nonzero.

Virtual tables cannot declare foreign keys. Triggers on the source tables remove
vectors when sources are deleted (including cascading note deletes) or content
changes. The NCP indexer then re-embeds changed examples. Knowledge ingestion
replaces chunks and their vectors together in one transaction.

Autogeneration ignores vec0 tables and their internal shadow tables. Write manual
Alembic operations for vector schema changes and model/width changes, including
any required re-embedding. Never edit sqlite-vec's shadow tables directly.

Downgrading to `0001` discards vectors but keeps source content. Downgrading to
`base` deletes the relational tables as well; use only disposable databases.
