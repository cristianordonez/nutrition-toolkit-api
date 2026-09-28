# Bundled offline embeddings

The engine uses `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).
Its logical database model ID remains
`sentence-transformers:sentence-transformers/all-MiniLM-L6-v2`; paths are never
stored as model IDs. The model's own Normalize module is retained, and encoding
still uses `normalize_embeddings=False`, as the previous Pydantic AI adapter did.

## Prepare assets once, before development or distribution builds

From the repository root:

```sh
uv run --package engine python apps/desktop/engine/scripts/prepare_embedding_model.py
```

This is the **only download step**. The tracked manifest at
`src/engine/assets/models/minilm.json` pins the upstream commit and every file's
SHA-256. The script stages and validates the safetensors weights, tokenizer,
module/config files, original model card, and Apache 2.0 license, then copies real
files (not cache symlinks) into:

```text
apps/desktop/engine/src/engine/assets/models/all-MiniLM-L6-v2/
```

The generated directory is approximately 88 MiB and is gitignored. It must be
prepared on each fresh checkout/build machine, or supplied as a build artifact.
The preparation script can use the build machine's HF cache; runtime never does.
For an offline build, pass `--source /path/to/snapshot` containing every manifest
file, including `LICENSE.txt`. Assets are checksum-verified either way. Build
preparation requires the engine dependencies (including `huggingface_hub`, which
Sentence Transformers installs); release packaging itself never downloads models.

## Development and installed packages

`engine.paths.bundled_embedding_model_dir()` resolves assets relative to the
installed package's `__file__`, not the working directory, user data, or HF cache.
Editable installs use the source directory above. Wheels use
`site-packages/engine/assets/models/all-MiniLM-L6-v2/`.

The embedding service lazily creates one `SentenceTransformer` per engine
process, from that local directory with `local_files_only=True`, and serializes
loading/inference. Missing files raise `EmbeddingUnavailableError` with repair
instructions. No runtime cache/download fallback or global offline environment
switch is used. Other model providers are unaffected.

## Packaging on macOS and Windows

```sh
uv build --package engine
```

The Hatch build hook checksum-validates and explicitly includes all pinned
model assets in **both wheels and source distributions**, despite `.gitignore`.
Missing/corrupt assets fail the build. It includes the
[default database](#default-database) the same way. Editable installs remain possible before
asset preparation. The model files are platform-independent; native dependencies
such as PyTorch/tokenizers must match the target OS and architecture.

The `pyinstaller40` entry point supplies `hook-engine.py` to collect the model
data at the same package-relative path in a frozen build and include dynamically
imported MiniLM/BERT modules. This works with PyInstaller's `__file__` layout on
both macOS and Windows, without writable model directories or hard-coded paths.
Run the offline smoke check on each native release target; macOS signing and
Windows installer/sidecar packaging still apply to the whole application.

**Existing desktop limitation:** Tauri currently invokes `uv` from the source
checkout. This change does not turn it into a standalone release launcher.
Connecting a frozen engine sidecar via `bundle.externalBin` and replacing that
dev launcher remains necessary before distributing a self-contained `.app`/`.exe`.
The engine wheel/sdist does contain the model; Tauri alone does not yet package
the engine. See the desktop README's sidecar section.

## Default database

A fresh install does not start empty. The engine ships a starter SQLite
database at `src/engine/assets/reference/facts.db` holding reference data only:

- the knowledge base (diet and nutrition-care manual chunks),
- the NCP style examples (`ncp_note` rows with status `example`),
- the vectors for both, and the enteral formula catalog.

On startup, `initialize_database()` copies it to the user's database path
(`~/Library/Application Support/NutritionToolkit/facts.db` on macOS, or
`NTK_DATABASE_PATH`) **only when no file exists there**, then runs migrations
and seeds defaults as usual. An existing database is never replaced or merged
into, whatever it holds. To pick up a newer default on a machine that already
has a database, move the old file aside (with its `-wal`/`-shm` files) and
run any command.

A source checkout without the starter file simply starts from an empty
database. Tests that pass their own engine never use it.

### Rebuild it

After ingesting knowledge or NCP examples into your local database, rebuild the
starter from it. From the repository root:

```sh
uv run --package engine python apps/desktop/engine/scripts/build_reference_database.py
```

This reads the configured database (`NTK_DATABASE_PATH` or the platform
default); pass `--source /path/to/facts.db` to build from another file. The
script:

- snapshots the source with `VACUUM INTO`, leaving the source untouched;
- **refuses** the build if any table other than the knowledge, NCP-note,
  formula and settings tables has rows, if any NCP note is not an example or
  is linked to a person or facility, or if any chunk or example has no vector;
- drops the settings row, so new users get the default settings;
- writes a single compacted file (no WAL) and checks its integrity.

The script never deletes clinical data to make a file pass. Build from a
database used only for curating reference data, never one with residents in
it. The example notes come from deidentified reports and are scrubbed on
ingest, but scrubbing is best-effort, so review what goes in.

The file (about 23 MB) is committed to git, so a fresh checkout can build
without running the script. After changing the knowledge base or NCP
examples, rebuild it and commit the result. The Hatch build hook and the
PyInstaller hook both include it, and both fail the build when it is missing.

## Verify offline behavior

After preparing the model, disconnect networking and run:

```sh
uv run --no-sync --package engine python apps/desktop/engine/scripts/verify_offline_embeddings.py
uv run --no-sync pytest apps/desktop/engine/tests/services/test_embedding_loader.py
```

The smoke check starts with empty HF/Transformers caches, deliberately unsets
global offline flags, blocks and records socket/DNS and `httpx` requests, and
exercises real first-load, document, query, and async repeated inference. It
checks 384-dimensional normalized outputs and instance reuse. Success prints
`"network_attempts": []`. It does not open a patient database. Run it with the
installed release wheel too, outside the repository, to verify package contents.

For a native packaging smoke check (not a replacement for the Tauri sidecar):

```sh
uv run --package engine --with pyinstaller pyinstaller --onedir --name offline-embedding-check apps/desktop/engine/scripts/verify_offline_embeddings.py
dist/offline-embedding-check/offline-embedding-check
```

On Windows run `dist\offline-embedding-check\offline-embedding-check.exe`.
The probe calls `multiprocessing.freeze_support()` before importing ML code;
the eventual frozen CLI entry point should do the same.

References: [SentenceTransformer local loading](https://sbert.net/docs/package_reference/sentence_transformer/model.html),
[PyInstaller package-relative data](https://pyinstaller.org/en/stable/runtime-information.html).

## Knowledge chunking and re-ingestion

Knowledge extraction preserves PDF text blocks and bookmark hierarchy (including
the NCM manuals' dot-indented bookmarks). Printed navigation is context, not a
separate chunk. The processor excludes empty divider pages, front matter and
reference lists, retains paragraphs/lists/table values, and carries physical PDF
page ranges through multi-page articles into each resulting chunk.

Chunk windows use the bundled MiniLM tokenizer and its 256-token input limit,
including breadcrumb context and special tokens. Paragraph/sentence boundaries
are preferred, with bounded overlap when needed. Only tokenizer assets are loaded
for chunking; embedding inference still uses the one centralized model instance.

Existing stored chunks are not rebuilt automatically. After changing the chunking
strategy, re-ingest each manual with `--overwrite` to replace its chunks and
vectors (without resetting the database):

```sh
uv run --package engine engine knowledge ingest --path /path/to/NCM2026.pdf --document-type nutrition-care-manual --overwrite
uv run --package engine engine knowledge ingest --path /path/to/NCM2026_DietManual.pdf --document-type diet-manual --overwrite
```
