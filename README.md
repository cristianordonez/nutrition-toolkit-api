# Nutrition Toolkit API

A monorepo split into a cloud API and an on-device desktop engine for
generating Nutrition Care Process (NCP) notes.

## Architecture

This repository is a [uv workspace][uv-workspace] (a monorepo of packages sharing one
lockfile and one virtual environment) rather than a single installable package:

- The root `pyproject.toml` is a **virtual workspace root** — it has no `[project]`
  table of its own. It only declares the workspace members (`tool.uv.workspace`) and
  holds configuration shared across every package in the repo: dev `dependency-groups`,
  and the `tool.ruff`, `tool.ty`, `tool.pytest`, `tool.coverage`, and `tool.codespell`
  settings.
- [`packages/ntk-core`](packages/ntk-core) is a shared, pure-Pydantic library (the
  `ntk` Python package) — table-less schemas, calculators, and generic infra used by
  both apps below. It has no console scripts and is never run on its own.
- [`apps/cloud-api`](apps/cloud-api) is the cloud service (the `api` package) — it
  generates NCP notes via OpenAI + pydantic-ai and owns Postgres/pgvector.
- [`apps/desktop`](apps/desktop) is the desktop app. Its Python backend,
  [`apps/desktop/engine`](apps/desktop/engine) (the `engine` package), runs on the
  user's device: it extracts structured clinical facts from uploaded documents and
  owns all person/clinical data locally in SQLite. `apps/desktop/src` /
  `apps/desktop/src-tauri` hold the (not yet wired up) Tauri frontend.

Because all members resolve into a single `uv.lock`, `uv sync` and `uv run` from the
repository root install and run against every package at once — see below for
package-scoped variants of these commands. See [uv workspaces][uv-workspace] for
further details.

## Running the apps

### The whole stack at once

```bash
tox -e up          # Postgres + Redis + migrations + cloud-api, in dependency order
tox -e api-key     # mint a key for the desktop engine, then put it in .env
cd apps/desktop && npm run tauri dev   # the desktop window
```

`tox -e up` waits for each service to pass its healthcheck and applies migrations
before cloud-api starts, so the API is ready to serve when the command returns.
`tox -e logs` follows cloud-api, `tox -e down` stops everything (`tox -e down -- -v`
also drops the data volumes).

The desktop app is not containerized on purpose: it is a native window that owns
local SQLite databases on your machine, so it runs on the host.

Two settings connect the halves. Put the key from `tox -e api-key` in
`NTK_CLOUD_API_KEY`, and leave `NTK_USE_LOCAL_GENERATION=false` so notes are
generated cloud-side. Setting it to `true` generates them in the engine instead —
useful offline, but it skips the diet and nutrition-care manual lookups, which
search a knowledge base that only exists cloud-side.

### Individual packages

Each package's own README has full setup/configuration details and every available
command; this is the quick-reference version, runnable from the repository root.

| Package | README | Run |
| --- | --- | --- |
| `apps/cloud-api` (`api`) | [apps/cloud-api/README.md](apps/cloud-api/README.md) | `uv run --package api api --help` (CLI) · `uv run --package api api-server` (server) |
| `apps/desktop/engine` (`engine`) | [apps/desktop/README.md](apps/desktop/README.md) | `uv run --package engine engine --help` (CLI) |
| `packages/ntk-core` (`ntk`) | [packages/ntk-core/README.md](packages/ntk-core/README.md) | shared library — nothing to run, see its README for testing/linting |

```bash
# cloud-api: start the FastAPI server (add --dev for autoreload)
uv run --package api api-server

# cloud-api: CLI controller groups (ncp, calc, key, knowledge)
uv run --package api api --help

# desktop engine: CLI controller groups (document, persons, ncp, tubefeed, demo)
uv run --package engine engine --help
```

## Development

- System python is available at /usr/bin/python3

- Python shim created using pyenv is available at ~/.pyenv/shims. View all available shims with following command:

```bash
pyenv versions
```

- Virtual environments are managed with uv. Create new virtual environment and install new python versions with the following command:

```bash
uv venv
uv python install <version>
```

- View all available uv managed python versions with the following command:

```bash
uv python list
```

- Install the workspace (all packages under `packages/` and `apps/`) locally

```bash
uv sync
```

- Run an app's CLI or server with `uv run --package <name> <command>` from the
  repository root, or `cd` into the app and drop `--package <name>`. See
  [Running the apps](#running-the-apps) above.

- To add a dependency to a specific workspace package (e.g. `ntk-core`), run from the
  root of the repository:

```bash
uv add --package ntk-core pydantic
```

- Use docker compose to start postgresql and redis containers. `docker compose`
  reads its `.env` from the same directory as `docker-compose.yml` (the repository
  root), so copy the root `sample.env` there first:

```bash
cp sample.env .env   # then fill in the values
docker compose up -d
```

## Database Migrations

Alembic manages PostgreSQL schema migrations for `apps/cloud-api` — the only
package with a shared, persisted database (Postgres/pgvector). It is scoped there,
not at the repository root: `apps/desktop/engine` persists locally in SQLite with
no Alembic setup, and `packages/ntk-core` has no database at all.

```bash
cd apps/cloud-api
uv run alembic revision --autogenerate -m "describe the schema change"   # after changing a SQLModel table
uv run alembic upgrade head                                              # apply pending migrations
uv run alembic current                                                   # check the current revision
uv run alembic downgrade -1                                              # roll back one migration
```

See [`apps/cloud-api/alembic/README.md`](apps/cloud-api/alembic/README.md) for
full conventions (migration rules, destructive-change handling, deployment
workflow) and what to do with a pre-split database that still has `person`/
clinical tables.

## Pre-Commit

- Install pre-commit with uv

```bash
uv tool install pre-commit --with pre-commit-uv
```

- Install git-hooks scripts

```bash
pre-commit install
```

## Testing

- Install tox with uv

```bash
uv tool install tox --with tox-uv
```

- Using the tox command will run all pre-commit hooks which include linting, formatting and type checking the code base. To run a single pre commit hook use the following command:

```bash
pre-commit run <hook-id>
```

- Each package's test suite must run in its own `pytest` invocation (see the
  `tool.pytest` comment in this file's `pyproject.toml` for why — their
  command-group registries are process-global and can't share a process):

```bash
uv run pytest packages/ntk-core/tests
uv run pytest apps/cloud-api/tests
uv run pytest apps/desktop/engine/tests
```

- Lint and type-check the whole workspace directly (outside of tox/pre-commit).
  `ty` lives in its own `type` dependency group (kept separate from `dev` — see
  [Known Issues](#known-issues)), so pass `--group type` to reach it:

```bash
uv run ruff check .
uv run ruff format .
uv run --group type ty check
```

## Deployment

- Use the `api-server` command to run uvicorn on the cloud-api FastAPI app (see
  [`apps/cloud-api/README.md`](apps/cloud-api/README.md) for details):

```bash
uv run --package api api-server
```

- containerize the REST API using Docker:

```bash
docker build -t ntk-api-image .
docker run -d --env database_host=host.docker.internal --add-host=host.docker.internal:host-gateway -p 3000:3000 --name ntk-api ntk-api-image
```

- `apps/cloud-api`'s initial Alembic migration already enables the pgvector
  extension (`CREATE EXTENSION IF NOT EXISTS vector`) as part of `alembic upgrade
  head`, provided the migration role can create extensions. If it can't, an admin
  needs to run this once manually before migrating:

```PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;
```

## Known Issues

- Due to issues with using Ty with pre-commit due to the tox-uv integration, the type checking tox command must be separated from the linting and formatting check command

## References

- [uv workspaces][uv-workspace]
- [Customizaition][customization]
- [MCP Server][mcp-server]
- [Documentation with Readthedocs][readthedocs]
- [uv][uv]
- [Using Tox with UV][tox-uv]
- [Ruff integration][ruff]
- [Ty type checking][ty]
- [Sphinx][sphinx-rtd]
- [Logfire][logfire]

[uv-workspace]: https://docs.astral.sh/uv/concepts/projects/workspaces/
[customization]: https://code.visualstudio.com/docs/copilot/concepts/customization
[mcp-server]: https://modelcontextprotocol.io/extensions/apps/build#manual-setup
[readthedocs]: https://app.readthedocs.org/projects/nutrition-toolkit-api/
[uv]: https://docs.astral.sh/uv/concepts/tools/#tool-versions
[tox-uv]: https://github.com/tox-dev/tox-uv
[ruff]: https://docs.astral.sh/ruff/
[sphinx-rtd]: https://sphinx-rtd-tutorial.readthedocs.io/en/latest/sphinx-config.html
[ty]: https://docs.astral.sh/ty/
[logfire]: https://logfire-us.pydantic.dev/cristianordonez/nutrition-toolkit/agents/data_extraction_agent/metrics?last=%221d%22
