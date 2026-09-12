# Project

FastAPI/Python nutrition application using SQLModel.

The application ingests structured and unstructured clinical documents, persists normalized data, and generates nutrition assessments and recommendations.

## Architecture

Use the shortest appropriate dependency path.

```text
Simple:
Route → Service → Repository → Database

Workflow:
Route / CLI → Controller or Pipeline → Service / Repository / Agent
```

Not every operation needs every layer.

* Routes handle HTTP concerns and should remain thin.
* Controllers are optional. Use them for API/CLI shared entry points or orchestration across multiple components.
* Services contain reusable deterministic business logic and application operations.
* Pipelines own multi-step workflows.
* Repositories contain persistence and database query logic only.
* Agents contain LLM-based reasoning and should normally be invoked through a service or pipeline.
* Do not introduce architectural layers solely for consistency.
* Avoid broad refactors unrelated to the current task.

## Folder Responsibilities

### `routes/`

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

* resident document ingestion
* knowledge ingestion
* assessment generation
* historical assessment import
* report processing

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

* unstructured clinical text interpretation
* unknown document extraction
* nutrition assessment synthesis

Prefer deterministic Python for:

* calculations
* validation
* normalization
* known-format extraction
* filtering and ranking
* database retrieval
* context assembly
* token budgeting

Agents should receive focused context and should not own persistence.

### `models/`

SQLModel persistence models and domain data structures.

Models should primarily describe data rather than orchestrate application behavior.

### `schemas/`

API-specific request and response models when they do not naturally belong in the domain model layer.

### `calculators/`

Deterministic nutrition calculations such as energy requirements, BMI, ideal body weight, significant weight change, and tube feeding.

Keep tightly related calculation helpers and formatting with the calculator when appropriate.

### `extractors/`

Prefer domain-specific extractor folders:

```text
pipelines/
    resident/
        extractors/
    knowledge/
        extractors/
```

Use deterministic extraction for known formats and AI extraction for unknown or highly unstructured formats.

### `utils/`

Only small, broadly reusable utilities.

Keep domain-specific helpers with the service, calculator, pipeline, or domain that owns them.

### `cli/`

CLI entry points should reuse the same services and pipelines as the API.

Do not duplicate business logic between CLI and HTTP code.

## Dependency Rules

Valid dependency paths include:

```text
Route → Service → Repository
Route → Pipeline → Repository
CLI → Pipeline
Pipeline → Agent
Service → Repository
```

* Repositories must not depend on services, controllers, routes, or pipelines.
* Agents must not depend on routes or controllers.
* Domain calculations must not depend on HTTP or CLI layers.
* Prefer code placement based on what the code does, not where it is called from.
* Prefer cohesive modules over unnecessary abstraction layers.

## Database Migrations

Use Alembic as the only mechanism for persistent database schema changes.

* Do not use `SQLModel.metadata.create_all()` to manage application databases.
* Schema changes to SQLModel models require an Alembic migration.
* Generate migrations with `alembic revision --autogenerate -m "description"` and review the generated operations before applying them.
* Apply migrations with `alembic upgrade head`.
* Create new migrations for new schema changes rather than modifying already-applied migrations.
* Use manual Alembic operations when PostgreSQL-specific behavior is not represented correctly by autogenerate.
* Use `alembic check` when appropriate to detect model changes without migrations.
* Do not use `alembic stamp` as a substitute for running migrations unless the schema is already verified to match the target revision.
