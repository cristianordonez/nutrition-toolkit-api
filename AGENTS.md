# Project

This is a FastAPI/Python nutrition application.

The application ingests structured and unstructured clinical documents, normalizes data into SQLModel models, and generates nutrition assessments, nutrition diagnoses, nutrition interventions, and nutrition monitoring and evaluation recommendations from persisted data.

## Architecture

Use this dependency direction:

Route
→ Controller
→ Service / Pipeline
→ Repository / Agent
→ Database

Controllers should coordinate requests but should not contain business logic.

Controllers should not call AI agents directly.
Agents should normally be invoked through a service or pipeline.

For simpler routes that do not require an associated CLI command, directly call the service from the route. If more than two services need to be called, prefer using the controller -> services flow above.

Route
→ Service / Pipeline
→ Repository / Agent
→ Database

## SQLModel

Keep database relationships based on primary keys.

Do not introduce unnecessary schema migrations for simple application-level
refactors.

Before changing a model or unique constraint, inspect related migrations,
relationships, repositories, and tests.

## Async

Do not call `asyncio.run()` from code that may already execute inside an
async FastAPI event loop.

Prefer async all the way through an async call chain.

Do not create nested event loops.

## Performance

Large reports may contain many residents and many pages.

Avoid repeated parsing of the same PDF.

Avoid sending deterministic data through an LLM.

Before introducing multiprocessing or threading, verify that the work is actually CPU-bound or independently parallelizable.

Keep concurrency infrastructure separated from domain logic.

## Code Style

Use:

- Python 3.12+
- type hints
- Pydantic v2
- SQLModel
- FastAPI
- pytest

Prefer small cohesive methods.

Avoid broad refactors unless required by the task.

Do not introduce abstractions unless they remove real duplication or
clarify an architectural boundary.

## Testing

For every behavior change:

1. Add or update tests.
2. Run the smallest relevant test set first.
3. Run the broader suite when practical.

Typical commands:

```bash
tox -e py314
tox -e ruff
tox -e type
```
