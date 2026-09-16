# Project

A uv workspace split into a FastAPI backend and an on-device desktop engine
that together ingest clinical documents, persist normalized data, and generate
clinical notes. Shared modules are kept in the ntk-core package located in packages directory.

## Repository Structure

Three workspace packages, each with its own `pyproject.toml`, sharing one
`uv.lock`/venv:

```text
packages/ntk-core/   (import name: ntk)     shared, pure-Pydantic schemas, calculators, generic infra — no SQL tables, no app coupling
apps/cloud-api/      (import name: api)     cloud service — Postgres/pgvector, FastAPI, OpenAI NCP generation
apps/desktop/engine/ (import name: engine)  on-device engine — SQLite, document extraction, no HTTP server
```

**`packages/ntk-core`** is the one dependency both apps share. It holds table-less
Pydantic schemas, calculators (`ntk.calculators.nutrition_calculator`), and generic
infra (`ntk.controllers.base/registry/uploads`, `ntk.utils.*`, `ntk.logger`). It
must never gain a SQLModel table, an app-specific dependency (FastAPI, psycopg,
pgvector, sentence-transformers), or an import from `api.*`/`engine.*`.

**`apps/cloud-api`** never persists clinical or patient data.

**`apps/desktop/engine`** owns all person/clinical data locally in duckDB using an in-memory database.
May call `apps/cloud-api` over HTTP (`engine.clients.cloud_api_client.CloudAPIClient`) to generate final report from context. Patient-specific deterministic calculations (tube-feed rate/formula selection, energy needs, parenteral nutrition) run entirely here, backed by a local, non-PHI reference catalog (`engine.data.enteral_formulas.LocalFormulaCatalog`) — never send raw feeding records or other clinical inputs to the cloud merely to compute something deterministic.

**Cross-package rules:**

* `api.*` must never import `engine.*`, and `engine.*` must never import `api.*`.
  The only thing they share is `ntk.*` and the HTTP contract between them.
* `ntk.controllers.registry.COMMAND_REGISTRY` is a process-global dict. Both
  `api` and `engine` register a command group named `ncp`, so importing both into
  the same Python process raises `ValueError: Command group 'ncp' is already
  registered`. Never write a script, test, or tool that imports both — this is
  expected and by design, not a bug to work around.
* Cloud never imports engine's SQLAlchemy-mapped classes (it has no matching
  database). The wire contract between them is a set of table-less Pydantic
  mirror classes in `ntk.models.ncp_context` (`_ClinicalRecordDTO` subclasses) —
  engine converts its SQLModel instances to these with
  `Model.model_validate(orm_instance)` when assembling a request; cloud parses
  JSON straight into the same classes. Add a new clinical field to both the
  SQLModel table (engine) and its DTO mirror (ntk-core) together, keeping field
  names identical.
* Each package's test suite must run in its own `pytest` invocation (see the
  `tool.pytest` comment in the root `pyproject.toml`) — never combine two
  packages' tests in one process.

## Architecture

Within each app, use the shortest appropriate dependency path.

```text
Simple:
Route → Service → Repository → Database

Workflow:
Route / CLI → Controller or Pipeline → Service / Repository / Agent
```

Not every operation needs every layer.

* Routes handle HTTP concerns and should remain thin. Only `apps/cloud-api` has
  routes/a server; `apps/desktop/engine` is CLI/library only.
* Controllers are optional. Use them for API/CLI shared entry points or orchestration across multiple components.
* Services contain reusable deterministic business logic and application operations.
* Pipelines own multi-step workflows.
* Repositories contain persistence and database query logic only.
* Agents contain LLM-based reasoning and should normally be invoked through a service or pipeline.
* Do not introduce architectural layers solely for consistency.
* Avoid broad refactors unrelated to the current task.

## Folder Responsibilities

Each app (`apps/cloud-api/src/api/`, `apps/desktop/engine/src/engine/`) follows
this same internal layout; `packages/ntk-core/src/ntk/` only has the subset that
makes sense for a pure library (`models/`, `calculators/`, `controllers/`
base/registry/uploads, `utils/`, `pipelines/extraction.py`).

### `presentation/api/routers/` (cloud-api only)

FastAPI HTTP entry points.

Handle request parsing, dependency injection, authentication, status codes, and response models.

Simple routes may call services or pipelines directly.

### `controllers/`

Application-level orchestration, especially when an operation is shared between API and CLI or coordinates multiple services/pipelines.

Controllers should not contain business logic or call agents directly.

Do not create controllers that only forward arguments unless CLI exposure requires one.

### `services/`

Reusable deterministic operations such as:

* transformations
* validation
* domain rules
* persisted-data operations
* coordination of closely related repository calls

Do not use services as meaningless wrappers.

### `pipelines/`

Multi-step workflows such as:

* person document ingestion (engine)
* knowledge ingestion (cloud-api)
* NCP generation (cloud-api)
* NCP import from clinical-note reports (engine; the promotion-to-searchable-cloud-NCP step is currently deferred, see `NutritionCareProcessPipeline.sync_ncps()`)

Organize pipelines by domain and keep workflow-specific extractors/helpers nearby.

Do not create pipelines for simple CRUD operations.

### `repositories/`

Persistence and database query logic.

Repositories may retrieve, create, update, delete, and query models.

Repositories must not contain workflows, document parsing, unrelated business logic, or agent calls.

Share the request/CLI database session across repositories participating in the same operation.

### `agents/`

LLM-based extraction and reasoning.

Use agents for tasks that genuinely require language-model reasoning, such as:

* unstructured clinical text interpretation (engine's `data_extraction_agent`)
* unknown document extraction (engine)
* nutrition NCP synthesis (cloud-api's `ncp_agent`)

Prefer deterministic Python for:

* calculations
* validation
* normalization
* known-format extraction
* filtering and ranking
* database retrieval
* context assembly
* token budgeting

Agents should receive focused context and should not own persistence. The cloud
NCP agent in particular must never receive patient-specific energy needs,
feeding records, or other clinical inputs for the purpose of selecting a
formula/schedule — that decision is made on-device before the request is sent.

### `models/`

SQLModel persistence models and domain data structures.

Models should primarily describe data rather than orchestrate application behavior.

Only `apps/cloud-api` and `apps/desktop/engine` have SQLModel tables
(`models/sql/`); `packages/ntk-core`'s `models/` holds table-less Pydantic
schemas only (`ConfigDict`, no `table=True`).

### `calculators/`

Deterministic nutrition calculations such as energy requirements, BMI, ideal body weight, significant weight change, and tube feeding.

`ntk.calculators.nutrition_calculator` (generic energy/BMI/weight-basis math) is
shared in ntk-core. Patient-specific calculators that need clinical records or
the local formula catalog (tube-feed, parenteral nutrition, weight-history) live
in `engine.services.calculators` — do not move these to ntk-core or cloud-api.

Keep tightly related calculation helpers and formatting with the calculator when appropriate.

### `extractors/`

Prefer domain-specific extractor folders, e.g.:

```text
pipelines/
    person/
        ingestion/
            extract/
    knowledge/
        ingestion/
            extractors/
```

Use deterministic extraction for known formats and AI extraction for unknown or highly unstructured formats.

### `utils/`

Only small, broadly reusable utilities. These belong in `ntk.utils.*` if both
apps could plausibly use them.

Keep domain-specific helpers with the service, calculator, pipeline, or domain that owns them.

### `presentation/cli/` (`cli/`)

CLI entry points should reuse the same services and pipelines as the API/other
CLI commands within the same app.

Do not duplicate business logic between CLI and HTTP code, and never share a CLI
entry point between `api` and `engine` (see the process-global registry rule
above).

## Dependency Rules

Valid dependency paths include:

```text
Route → Service → Repository            (cloud-api)
Route → Pipeline → Repository            (cloud-api)
CLI → Pipeline                           (either app)
CLI → Controller → Service / Repository  (either app)
Pipeline → Agent                         (either app)
Service → Repository                     (either app)
Engine pipeline/service → CloudAPIClient → HTTP → cloud-api route (never a direct Python import)
```

* Repositories must not depend on services, controllers, routes, or pipelines.
* Agents must not depend on routes or controllers.
* Domain calculations must not depend on HTTP or CLI layers.
* `api.*` and `engine.*` must never import each other (see Cross-package rules above) — the only path between them is HTTP.
* Prefer code placement based on what the code does, not where it is called from.
* Prefer cohesive modules over unnecessary abstraction layers.

## Database Migrations

Alembic manages schema for `apps/cloud-api`'s Postgres database only — it lives
in `apps/cloud-api/alembic/`, not at the repository root. See
[`apps/cloud-api/alembic/README.md`](apps/cloud-api/alembic/README.md) for the
full workflow and rules; the short version:

* Use Alembic as the only mechanism for `apps/cloud-api`'s persistent schema changes.
* Do not use `SQLModel.metadata.create_all()` to manage its database.
* Schema changes to `api.models.sql` require an Alembic migration.
* Generate migrations with `cd apps/cloud-api && uv run alembic revision --autogenerate -m "description"` and review the generated operations before applying them.
* Apply migrations with `uv run alembic upgrade head`.
* Create new migrations for new schema changes rather than modifying already-applied migrations.
* Use manual Alembic operations when PostgreSQL-specific behavior is not represented correctly by autogenerate.
* Do not use `alembic stamp` as a substitute for running migrations unless the schema is already verified to match the target revision.

`apps/desktop/engine`'s SQLite databases (facts + settings) currently have no
migration tooling at all — a separate, SQLite-appropriate migration setup for
them is planned but not yet built. Do not reach for Alembic there until that
lands; `engine.database.db.initialize_database()` documents the current
(intentionally minimal) state.
