# ntk-core

[← workspace root](../../README.md)

Shared, pure-Pydantic domain schemas, calculators, and generic infrastructure used
by both [`apps/cloud-api`](../../apps/cloud-api/README.md) and
[`apps/desktop/engine`](../../apps/desktop/README.md) (the Python import name is
`ntk`). It holds no SQLModel tables and has no Postgres/pgvector/redis/FastAPI
coupling — it is the one schema both apps agree on byte-for-byte for the wire
contract between them.

This is a library, not an application: it has no console scripts and nothing to
launch. "Running" it means running its test suite or its checks.

## Setup

Run these from the repository root.

```bash
uv sync
```

## Testing

```bash
uv run pytest packages/ntk-core/tests
```

`packages/ntk-core/tests/test_parallel.py`'s `mode=process` test can deadlock when
combined with a heavier app's suite (pydantic-ai/sentence-transformers/logfire
imports) in the same pytest process — always run this package's tests in their own
invocation, as above, not alongside `apps/cloud-api/tests` or
`apps/desktop/engine/tests`.

## Linting and type checking

```bash
uv run ruff check packages/ntk-core
uv run --group type ty check
```

`ty` lives in its own `type` dependency group (not included in `dev`), so it needs
`--group type` to be resolved.

## Using it from another workspace package

`ntk-core` is resolved as a workspace member. Depend on it with:

```toml
[project]
dependencies = ["ntk-core"]

[tool.uv.sources]
ntk-core = { workspace = true }
```

and import it as `ntk`, e.g. `from ntk.calculators.nutrition_calculator import
NutritionCalculator`.
