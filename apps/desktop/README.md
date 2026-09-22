# desktop

[← workspace root](../../README.md)

The desktop application. Two pieces live here:

- [`engine`](engine) — the Python backend (package `engine`). Runs on the user's
  device: extracts structured clinical facts from uploaded documents (via OpenAI
  today; an on-device/llama.cpp model is a planned future swap), owns all
  person/clinical data locally in SQLite, and calls the
  [cloud API](../cloud-api/README.md) over HTTP to generate Nutrition Care Process
  notes from that local data.
- `src` / `src-tauri` — the Tauri 2 desktop shell (React + TypeScript + Vite). Today
  it is an empty frame: it opens a window and probes the engine to prove the
  desktop → engine seam works. See [Running the desktop app](#running-the-desktop-app).

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

## Running the desktop app

### Prerequisites

On top of the `uv sync` and `.env` steps in [Setup](#setup):

| Tool | Why | Install |
| --- | --- | --- |
| Node 20+ | Vite dev server and the React frontend | [nodejs.org](https://nodejs.org) |
| Rust (stable) | Tauri compiles the shell as a native binary | [rustup.rs](https://rustup.rs) |

`NTK_OPEN_AI_API_KEY` must be set to a **non-empty** value in
`apps/desktop/engine/.env`. The engine builds its OpenAI client at import time,
so with a blank key it fails to start at all and the app reports the engine as
unavailable — even for something as simple as asking its version.

### Start it

From this directory (`apps/desktop`):

```bash
npm install          # first run only
npm run tauri dev
```

The first launch compiles the Rust shell from scratch and takes a few minutes;
later runs are seconds. The window opens once the build finishes.

While it runs, `src/` changes hot-reload in place and changes under `src-tauri/`
trigger a Rust rebuild and relaunch the window — expect the app to disappear and
come back for a moment when you edit Rust.

To stop it: close the window, or `pkill -f nutrition-toolkit-desktop`.

### Build a bundle

```bash
npm run tauri build
```

Output lands in `src-tauri/target/release/bundle/`. Note the dev-only sidecar
caveat below — a bundle built today still shells out to `uv` and will not run on
a machine without this checkout.

### Where the app keeps its files

Standard per-platform application directories, so nothing lives in a dotfile
in `$HOME`:

| | macOS |
| --- | --- |
| Databases | `~/Library/Application Support/NutritionToolkit/` |
| Logs | `~/Library/Logs/NutritionToolkit/engine.log` |

Linux uses `~/.local/share` and `~/.local/state`; Windows uses `%LOCALAPPDATA%`.
`NTK_FACTS_DATABASE_PATH`, `NTK_SETTINGS_DATABASE_PATH`, and `NTK_LOG_FILE`
override any of them.

Installs that predate this used `~/.nutrition-toolkit`. Those files are moved
into the data directory on the next run, and the old directory is removed once
it is empty. A file is never moved over one that already exists.

To watch the log while using the app:

```bash
tail -f ~/Library/Logs/NutritionToolkit/engine.log
```

Note the engine logs at INFO by default, so routine commands are quiet; the
desktop app does not pass `--debug` today.

### If the app shows "Engine unavailable"

The badge in the header is the engine probe. Hover it for the underlying error.
Common causes, in the order worth checking:

1. `NTK_OPEN_AI_API_KEY` is blank or missing — see above.
2. `uv` is not on `PATH` for the process that launched the app.
3. Dependencies are not installed — run `uv sync` from the repository root.

To see the same failure directly, run what the shell runs:

```bash
uv run --package engine engine --version   # from the repository root
```

### How the shell reaches the engine

The window is intentionally empty apart from a badge showing the engine's
version, which exists to prove the seam end to end rather than assume it.

The frontend never shells out itself. It calls a Tauri command
(`invoke("engine_version")`), and [`src-tauri/src/engine.rs`](src-tauri/src/engine.rs)
runs the Python CLI on its behalf. Keeping that boundary in one Rust file means
the frontend contract does not change when the packaging does.

Today that file runs `uv run --package engine engine …` from the workspace root.
It runs from the root on purpose: `logfire.configure()` looks for `.logfire/`
relative to the working directory. Since the engine's `.env` is resolved against
the working directory too, the shell passes `NTK_CONFIG_FILE` explicitly when
`apps/desktop/engine/.env` exists, so the file Setup tells you to create is the
one actually read. Without it, discovery falls back to a root-level `.env`.

**This is dev-only.** It needs `uv`, Python, and the source tree on the machine,
and an `.app` launched from Finder gets a minimal `PATH` that generally cannot
find `uv`. Before shipping, build `engine` into a standalone binary with
PyInstaller, name it for the target triple (`engine-aarch64-apple-darwin`),
declare it under `bundle.externalBin` in `tauri.conf.json`, and swap the
`Command` in `engine.rs` for the sidecar API.

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
