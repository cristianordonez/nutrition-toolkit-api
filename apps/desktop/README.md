# desktop

[← workspace root](../../README.md)

The desktop application. Two pieces live here:

- [`engine`](engine) — the Python backend (package `engine`). Runs on the user's
  device: extracts structured clinical facts from uploaded documents (via OpenAI
  today; an on-device/llama.cpp model is a planned future swap), owns all
  person/clinical data locally in SQLite, and calls the
  [cloud API](../cloud-api/README.md) over HTTP to generate Nutrition Care Process
  notes from that local data.
- `src` / `src-tauri` — the Tauri frontend. Not yet wired up; there is nothing to run
  here today.

Depends on the shared [`packages/ntk-core`](../../packages/ntk-core/README.md)
library (wire DTOs, calculators, generic infra) via the uv workspace.

## Setup

Run these from the repository root unless noted otherwise.

```bash
uv sync
cp apps/desktop/engine/sample.env apps/desktop/engine/.env   # then fill in the values
```

See `apps/desktop/engine/sample.env` for every setting (`NTK_OPEN_AI_API_KEY`,
`NTK_CLOUD_API_BASE_URL` — where `engine` calls `apps/cloud-api`,
`NTK_DOCUMENT_INGESTION_POOL_MODE`, `NTK_DOCUMENT_INGESTION_WORKERS`,
`NTK_CLINICAL_NOTE_EXTRACTION_CONCURRENCY`, `NTK_FACTS_DATABASE_PATH`,
`NTK_SETTINGS_DATABASE_PATH`, `NTK_LOCAL_MODEL_PATH` — unused seam for a future
on-device model). `NTK_CONFIG_FILE` (or running from
`apps/desktop/engine`) controls where `.env` is loaded from.

## Running the CLI

`engine` has no server process — it is a local CLI/library the (future) Tauri
frontend will call into. Everything is reachable through the `engine` console
script:

```bash
uv run --package engine engine --help
uv run --package engine engine document --help
uv run --package engine engine persons --help
uv run --package engine engine ncp --help
uv run --package engine engine tubefeed --help
```

Ingest a document into the local SQLite database:

```bash
uv run --package engine engine document ingest --files path/to/report.pdf
```

Developer workflow — extract local documents and print the exact NCP-generation
request JSON that `apps/cloud-api`'s `/nutrition-care-processes/generate` endpoint
expects, so it can be piped into a manual `curl` call against a running cloud-api
server:

```bash
uv run --package engine engine demo build-context --files path/to/report.pdf
```

## Testing

```bash
uv run pytest apps/desktop/engine/tests
```
