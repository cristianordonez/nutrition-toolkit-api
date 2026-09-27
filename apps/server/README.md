# server

[← workspace root](../../README.md)

The server application (Python package `server`). Generates Nutrition Care Process (NCP)
notes via OpenAI + a pydantic-ai agent, over a stateless HTTP boundary — it never
receives or persists raw person/clinical data, only the already-budgeted context the
[desktop engine](../desktop/README.md) sends it and the generated result. Owns
Postgres/pgvector.

Depends on the shared [`packages/ntk-core`](../../packages/ntk-core/README.md)
library (wire DTOs, calculators, generic infra) via the uv workspace.

## Setup

Run these from the repository root unless noted otherwise.

```bash
uv sync
cp apps/server/sample.env apps/server/.env   # then fill in the values
cp sample.env .env                                 # repo-root .env, for docker compose
docker compose up -d                               # starts Postgres + Redis
```

`NTK_CONFIG_FILE` (or running from `apps/server`) controls where `.env` is
loaded from; see `apps/server/sample.env` for every setting (`NTK_DATABASE_URL`,
`NTK_OPEN_AI_API_KEY`, `NTK_REDIS_DSN`, `NTK_PORT`, `NTK_DEBUG`, `NTK_POOL_SIZE`,
`NTK_MAX_OVERFLOW`). `NTK_DATABASE_URL` must point at the same Postgres instance
docker compose starts using the repo-root `.env` — see the root
[sample.env](../../sample.env) and [README.md](../../README.md#development).

Once Postgres is up, create the schema before starting the server for the first
time — see [Database Migrations](#database-migrations) below.

## Database Migrations

Alembic manages this app's Postgres schema; it lives in `apps/server/alembic/`
and is scoped to this app only (`apps/desktop/engine`'s local SQLite has no
migration tooling). Run these from inside `apps/server`:

```bash
cd apps/server
uv run alembic upgrade head                                              # create/update the schema
uv run alembic revision --autogenerate -m "describe the schema change"   # after changing a SQLModel table
uv run alembic current                                                   # check the current revision
```

See [`apps/server/alembic/README.md`](alembic/README.md) for the full
workflow, migration rules, and how to handle a database still on the pre-split
schema.

## Running the CLI

The `server-cli` console script exposes the same controllers the HTTP API uses:

```bash
uv run --package server server-cli --help
uv run --package server server-cli ncp --help
uv run --package server server-cli calc --help
uv run --package server server-cli key --help
uv run --package server server-cli knowledge --help
```

For example, to create an API key:

```bash
uv run --package server server-cli key create --help
```

## Running the server

```bash
uv run --package server server
```

This starts uvicorn on `server.presentation.api.main:app` (port from `NTK_PORT`,
default `8000`). Pass `--dev` for autoreload, `--host`/`--port` to override the
bind address:

```bash
uv run --package server server --dev --port 8000
```

Interactive API docs are then available at `http://localhost:8000/docs`.

## Testing

```bash
uv run pytest apps/server/tests
```
