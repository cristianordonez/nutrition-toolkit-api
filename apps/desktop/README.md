# desktop

[← workspace root](../../README.md)

The desktop application. Two pieces live here:

- [`engine`](engine) — the Python backend (package `engine`). Runs on the user's
  device: extracts structured clinical facts from uploaded documents (via OpenAI
  today; an on-device/llama.cpp model is a planned future swap), owns all
  person/clinical data locally in SQLite, and calls the
  [server](../server/README.md) over HTTP to generate Nutrition Care Process
  notes from that local data.
- `src` / `src-tauri` — the Tauri 2 desktop shell (React + TypeScript + Vite). Three
  tabs: **Notes** (drag in documents, ingest them, pick residents, generate a note
  per resident with optional per-resident context), **Energy** (calorie, protein and
  fluid needs from typed-in measurements) and **Tube feeding** (a formula picker and
  a paste-ready feeding order). See [Running the desktop app](#running-the-desktop-app).

Depends on the shared [`packages/ntk-core`](../../packages/ntk-core/README.md)
library (wire DTOs, calculators, generic infra) via the uv workspace.

## Setup

Run these from the repository root unless noted otherwise.

```bash
uv sync
cp apps/desktop/engine/sample.env apps/desktop/engine/.env   # then fill in the values
```

`apps/desktop/engine/sample.env` documents every setting with its default. The
ones that matter on a first run:

| Setting | Required? | Why |
| --- | --- | --- |
| `NTK_SERVER_BASE_URL` | Defaults to `http://localhost:8000` | Where server is reachable. |
| `NTK_SERVER_API_KEY` | Yes, to generate notes | Bearer token for server. Mint with `tox -e api-key`. |
| `NUTRITION_AI_LLAMA_URL` | No | Where Local AI's llama-server listens (default `http://127.0.0.1:8080`). See [AI providers](../../docs/local-ai.md). |
| `NTK_DATABASE_PATH` | No | Overrides the unified local SQLite database path. |

**Where this file is read from.** `ntk.models.base.get_env_file()` resolves
`$NTK_CONFIG_FILE`, and otherwise falls back to `<cwd>/.env`. The Tauri shell
sets `NTK_CONFIG_FILE` to `apps/desktop/engine/.env` when that file exists, so
creating it keeps the desktop app's settings separate from the compose stack's.
Without it, a command run from the repository root reads the root `.env`
instead — which works, but means one file serves both.

**Note generation needs server running.** It happens there and nowhere else,
because the diet and nutrition-care manual lookups search a pgvector knowledge
base that only exists server-side. There is deliberately no on-device note
agent, so generation fails with a clear error rather than quietly producing a
note without those lookups. Start it with `tox -e up` from the repository root.

## Running the desktop app

### Prerequisites

On top of the `uv sync` and `.env` steps in [Setup](#setup):

| Tool | Why | Install |
| --- | --- | --- |
| Node 20+ | Vite dev server and the React frontend | [nodejs.org](https://nodejs.org) |
| Rust (stable) | Tauri compiles the shell as a native binary | [rustup.rs](https://rustup.rs) |

No API key is needed: inference runs on-device by default through Local AI
(see [docs/local-ai.md](../../docs/local-ai.md)). Start llama-server before
the app -- `llama-server -m <model.gguf> --host 127.0.0.1 --port 8080` -- the
app does not start it.

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
`NTK_DATABASE_PATH` and `NTK_LOG_FILE` override their default locations.

The first run with no database there installs the bundled default database,
which already holds the knowledge base and NCP examples; see
[Default database](engine/README.md#default-database) for what it contains
and how to rebuild it:

```bash
uv run --package engine python apps/desktop/engine/scripts/build_reference_database.py
```

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

1. `uv` is not on `PATH` for the process that launched the app.
2. Dependencies are not installed — run `uv sync` from the repository root.

To see the same failure directly, run what the shell runs:

```bash
uv run --package engine engine --version   # from the repository root
```

### How the shell reaches the engine

The frontend never shells out itself. It calls a Tauri command — `invoke("…")` —
and [`src-tauri/src/engine.rs`](src-tauri/src/engine.rs) runs the Python CLI on
its behalf. Keeping that boundary in one Rust file means the frontend contract
does not change when the packaging does.

| Tauri command | Engine CLI |
| --- | --- |
| `engine_version` | `engine --version` |
| `ingest_documents` | `document ingest --files …` |
| `list_persons` | `persons list` |
| `generate_ncp` | `ncp generate --person-id … --note-type quarterly` |
| `calculate_energy` | `calculate energy …` |
| `calculate_tubefeed` | `tubefeed calculate …` |
| `list_formulas` | `tubefeed formulas` |
| `ai_status` | `ai status` |

Every one of these is declared `#[tauri::command(async)]`. A bare
`#[tauri::command]` runs on the main thread, and each of these blocks on a
Python subprocess — macOS composites the webview's frames on that same thread,
so a blocking command freezes the window and no spinner ever paints.

Two contracts hold this together, and breaking either is silent:

- **The engine's stdout is JSON and nothing else.** Controller results print
  there; logs, the Logfire banner and Logfire's span output all go to stderr.
  Logfire's console exporter defaults to *stdout*, so the CLI configures it
  onto stderr explicitly — otherwise any command that runs an agent emits span
  lines ahead of the JSON and the shell fails to parse it.
- **A formula is resolved by its exact catalog name.** Several products share a
  brand and strength, so a partial name matches more than one and the engine
  refuses it. The picker is populated from `list_formulas` for that reason, and
  filters by package type: ready-to-hang for a continuous order, cartons for a
  bolus one, matching what the calculator looks for.

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

For local embedding asset preparation and engine packaging, see
[Bundled offline embeddings](engine/README.md). Prepare the pinned model before
using knowledge search/ingestion or NCP example retrieval on a fresh checkout.

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
request JSON that `apps/server`'s `/nutrition-care-processes/generate` endpoint
expects, so it can be piped into a manual `curl` call against a running server
server:

```bash
uv run --package engine engine demo build-context --files path/to/report.pdf
```

## Testing

```bash
uv run pytest apps/desktop/engine/tests
```
