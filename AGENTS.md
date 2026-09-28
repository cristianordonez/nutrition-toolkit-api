# Project

A uv workspace holding a self-contained desktop application and a currently
disconnected HTTP server. The desktop app ingests clinical documents, persists
normalized data, and generates clinical notes, all on the user's device.

## Repository Structure

Two workspace packages, each with its own `pyproject.toml`, sharing one
`uv.lock`/venv:

```text
apps/desktop/engine/ (import name: engine)  the product — SQLite, document extraction, on-device agents, CLI only
apps/server/         (import name: server)  disconnected — Postgres, FastAPI, API-key management only
```

**`apps/desktop/engine`** is the whole running system. It owns all
person/clinical data locally in SQLite (`facts.db`), runs every agent, and
talks to nothing but the model provider. `apps/desktop/src` and
`apps/desktop/src-tauri` are its Tauri frontend; the shell reaches the engine
by running its CLI, never by importing it.

**`apps/server`** is kept but wired to nothing, and now does nothing the
engine cannot. Its pgvector knowledge base of the diet and nutrition-care
manuals was the last exception; the engine holds its own copy in
`models/sql/knowledge.py`, searched through `sqlite-vec` and shipped inside
the application bundle. Leave the server buildable and its tests passing; do
not add a dependency on it from `engine`, and port from it rather than
importing it.

Vector search on-device uses `sqlite-vec`, loaded onto every connection by the
`connect` hook in `engine.database.db`. Alembic creates `knowledge_chunk_vector`
and `ncp_note_vector` as `vec0` virtual tables. They are the only embedding
storage; there are no embedding SQLModel classes or duplicate BLOB tables.

* Vector width is fixed at 384 for the local `all-MiniLM-L6-v2` embedding model.
  Model or width changes require a new migration and re-embedding.
* Every vector row records its model. Search filters by it and narrows eligible
  source IDs inside the KNN query, before `k` limits the results.
* Migration-owned source-table triggers remove vectors on deletion or changed
  content. Repositories write vectors in the same transaction as their sources.
* Keep vec0 tables and their shadow tables out of SQLModel metadata and Alembic
  autogeneration. Their schema changes require manual migrations.
* Clinical sources are provenance records and are never embedded. NCP style
  examples live in `ncp_note` with status `example`; their vectors live in
  `ncp_note_vector`. Bundled examples have null `person_id` and
  `facility_id`.

**Cross-package rules:**

* `server.*` must never import `engine.*`, and `engine.*` must never import
  `server.*`. They share nothing at all — not a package, not a process, not a
  wire contract.
* Each app has its own `controllers.registry.COMMAND_REGISTRY`, a
  process-global dict. Both register a command group named `ncp`, so importing
  both into one Python process raises `ValueError: Command group 'ncp' is
  already registered`. Never write a script, test, or tool that imports both —
  this is expected and by design, not a bug to work around.
* Each package's test suite must run in its own `pytest` invocation (see the
  `tool.pytest` comment in the root `pyproject.toml`) — never combine two
  packages' tests in one process.

## Where inference runs

Exactly two providers, chosen by the user in Settings (`settings.ai_provider`):
`local` (default) -- a llama.cpp `llama-server` on this machine, reached at
`NUTRITION_AI_LLAMA_URL` -- or `openai` (hosted, with the user's own token in
the OS keychain via `engine.services.credentials`, never in SQLite). See
[docs/local-ai.md](docs/local-ai.md).

`engine.services.ai.controller.AIController` is the single place a provider is
chosen; agents ask it for a pydantic-ai `Model` (or `chat()`) and never know
which provider answered. Never put provider- or llama.cpp-specific logic in an
agent.

* A failing provider raises; never fall back to the other one, and never
  choose OpenAI on the user's behalf. OpenAI selected without a token is a
  configuration error, not a switch.
* The engine never starts, stops or locates llama-server; it only consumes
  the URL, which must be loopback. The
  desktop runtime will own the server's lifecycle.
* Never log or put in an error a prompt, completion, resident detail or raw
  provider output. Agent tracing runs with `include_content=False`.

Patient-specific deterministic calculations (tube-feed rate/formula selection,
energy needs, parenteral nutrition) never involve a model at all. They run
against a local, non-PHI reference catalog
(`engine.data.enteral_formulas.LocalFormulaCatalog`).

## Architecture

Within each app, use the shortest appropriate dependency path.

```text
Simple:
Route → Service → Repository → Database

Workflow:
Route / CLI → Controller or Pipeline → Service / Repository / Agent
```

Not every operation needs every layer.

* Routes handle HTTP concerns and should remain thin. Only `apps/server` has
  routes/a server; `apps/desktop/engine` is CLI/library only.
* Controllers are optional. Use them for API/CLI shared entry points or orchestration across multiple components.
* Services contain reusable deterministic business logic and application operations.
* Pipelines own multi-step workflows.
* Repositories contain persistence and database query logic only.
* Agents contain LLM-based reasoning and should normally be invoked through a service or pipeline.
* Do not introduce architectural layers solely for consistency.
* Avoid broad refactors unrelated to the current task.

## Folder Responsibilities

Both apps (`apps/server/src/server/`, `apps/desktop/engine/src/engine/`) use
this layout, each taking the parts it needs. Only `apps/server` has a
`presentation/` layer, because only it serves HTTP; the engine's CLI entry
point is a single `engine/cli.py` (see below).

### `presentation/api/routers/` (server only)

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
* NCP generation (engine)
* NCP import from clinical-note reports (engine)
* knowledge ingestion (server, disconnected)

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
* nutrition NCP synthesis (server's `ncp_agent`)

Prefer deterministic Python for:

* calculations
* validation
* normalization
* known-format extraction
* filtering and ranking
* database retrieval
* context assembly
* token budgeting

Agents should receive focused context and should not own persistence. The server
NCP agent in particular must never receive patient-specific energy needs,
feeding records, or other clinical inputs for the purpose of selecting a
formula/schedule — that decision is made on-device before the request is sent.

### `models/`

SQLModel persistence models and domain data structures.

Models should primarily describe data rather than orchestrate application behavior.

Both apps keep their SQLModel tables under `models/sql/`. The engine also
holds table-less Pydantic schemas directly in `models/` -- the wire and prompt
shapes (`models/ncp_context.py`), vocabulary (`models/clinical_vocab.py`) --
which describe data without persisting it.

### `calculators/`

Deterministic nutrition calculations such as energy requirements, BMI, ideal body weight, significant weight change, and tube feeding.

All of them live together in `engine.services.calculators`:
`nutrition_calculator` holds the generic energy/BMI/weight-basis math, which
takes measurements and returns numbers and is what the agent's calculator
toolset calls; tube-feed, parenteral nutrition and weight-history need
clinical records or the local formula catalog. Keep the generic ones pure
functions, but there is no reason to keep them in a separate package.

Their **result shapes** belong in `models/` (`models/energy_needs.py`), not
beside the calculator that returns them. `models.derived_calculations` carries
an `EnergyNeedsResult` on the person snapshot, so defining that type inside
the calculators package makes `models` import `services.calculators`, which
imports `models` back — a circular import that breaks every module importing
either one. A result type is a data shape with no behaviour, which is what
`models/` is for.

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

Only small, broadly reusable utilities, in that app's own `utils/`. The two
apps each carry their own copy; do not factor a shared package back out to
merge them.

Keep domain-specific helpers with the service, calculator, pipeline, or domain that owns them.

### CLI entry points

`apps/server` serves HTTP as well, so its CLI lives under
`presentation/cli/` alongside `presentation/api/`. `apps/desktop/engine` has no
server and never will -- it is a CLI and library only -- so a presentation
layer there would be one module in three directories. Its entry point is a
single `engine/cli.py`.

CLI entry points should reuse the same services and pipelines as the API/other
CLI commands within the same app.

Do not duplicate business logic between CLI and HTTP code, and never share a CLI
entry point between `server` and `engine` (see the process-global registry rule
above).

## Dependency Rules

Valid dependency paths include:

```text
Route → Service → Repository            (server)
Route → Pipeline → Repository            (server)
CLI → Pipeline                           (either app)
CLI → Controller → Service / Repository  (either app)
Pipeline → Agent                         (either app)
Service → Repository                     (either app)
```

The engine makes no call to the server. The only traffic leaving the device is
to the model provider, and only when a hosted model is switched on.

* Repositories must not depend on services, controllers, routes, or pipelines.
* Agents must not depend on routes or controllers.
* Domain calculations must not depend on HTTP or CLI layers.
* `server.*` and `engine.*` must never import each other (see Cross-package rules above) — the only path between them is HTTP.
* Prefer code placement based on what the code does, not where it is called from.
* Prefer cohesive modules over unnecessary abstraction layers.

## Database Migrations

Alembic manages each app's schema with independent environments and histories.
The server's Postgres migrations live in `apps/server/alembic/`. See
[`apps/server/alembic/README.md`](apps/server/alembic/README.md) for the
full workflow and rules; the short version:

* Use Alembic as the only mechanism for `apps/server`'s persistent schema changes.
* Do not use `SQLModel.metadata.create_all()` to manage its database.
* Schema changes to `server.models.sql` require an Alembic migration.
* Generate migrations with `cd apps/server && uv run alembic revision --autogenerate -m "description"` and review the generated operations before applying them.
* Apply migrations with `uv run alembic upgrade head`.
* Create new migrations for new schema changes rather than modifying already-applied migrations.
* Use manual Alembic operations when PostgreSQL-specific behavior is not represented correctly by autogenerate.
* Do not use `alembic stamp` as a substitute for running migrations unless the schema is already verified to match the target revision.

`apps/desktop/engine` uses one SQLite database for clinical data, local reference
data, and non-secret settings. Its revisions live in
`engine/database/migrations/`; `database/bootstrap.py` upgrades to head and seeds
defaults at CLI startup. `database/db.py` configures connections only, and
`database/sessions.py` owns session boundaries used by controllers and services.

A fresh install starts from `engine/assets/reference/facts.db`, which
`initialize_database()` copies into place only when the user's database file
does not exist, then migrates like any other. It holds reference data only --
knowledge base, NCP examples, their vectors, the formula catalog -- and is
built from a curated database by `scripts/build_reference_database.py`, which
refuses any file with person, facility, document or clinical rows. It is
committed to git and required by wheel and PyInstaller builds; rebuild and
commit it after changing the knowledge base or NCP examples.

The repository-root and engine-package-root `alembic.ini` files are development
entry points for the desktop database. Runtime bootstrap uses a programmatic
Alembic Config and packaged revisions. Never use `create_all()` for the running
application, import current models from a revision, or silently stamp/reset an
unversioned database. See the desktop migrations README for development commands
and the initial-schema boundary for legacy databases.
