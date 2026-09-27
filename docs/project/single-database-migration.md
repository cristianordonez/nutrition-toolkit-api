# One database, shipped with its reference content

Status: planned, in progress. No backwards compatibility: `facts.db` and
`settings.db` are both discarded and the device starts from the bundled file.
No Alembic — the schema is created by `create_all` against a single metadata,
and the shipped file is rebuilt rather than migrated.

## Why

`settings.db` held one table of six columns against thirty clinical tables,
and the split forced two engines, two sessions, two registries and two
migration stories. The reason to keep them apart was blast radius: wiping
clinical data to re-ingest would take the user's profile with it. Shipping a
default file changes that calculus — the database is no longer only a place
the device writes to, it is also content the app *ships*, and reference
content and user content want the same file so a query can join them.

What made the split defensible still has to be handled, not ignored:

* **PHI boundary.** One file means any copy of it is a PHI copy. The bundled
  file must contain no patient data, and nothing that exports "the database"
  can be treated as safe to attach to a bug report.
* **Write locking.** Every Tauri command is a separate engine process. A
  settings read during a twelve-minute ingest now contends with a writer on
  the same file. WAL mode makes readers non-blocking; writers still serialize.

## Blockers

1. **The 1000 NCPs must not be real resident notes.** They ship inside the
   `.app`, where anyone can extract them. Synthetic or properly de-identified
   only. This is the one item that cannot be designed around.
2. **Bundled vectors are locked to one embedding model.** Decided: bundle
   `nomic-embed-text` (768d) only. It works with no API key, no cost and no
   network on first run. Cloud users re-embed in the background.

## Vector search: sqlite-vec, without `vec0`

Staying on `sqlite-vec`, but only for its scalar distance functions. The
original plan put a `vec0` virtual table beside each vector table as the
index. Dropped: `vec0` has no approximate-nearest-neighbour structure, so its
`MATCH` is a full scan over a second copy of every vector, and at the corpus
sizes the device holds (hundreds of manual chunks, low thousands of examples)
that copy buys nothing but a table to keep in step.

Vectors are packed `float32` BLOBs in ordinary tables, and search scores them
in the query:

```sql
SELECT c.*, vec_distance_cosine(e.vector, :query) AS distance
  FROM knowledge_chunk_embedding e
  JOIN knowledge_chunk c ON c.id = e.knowledge_chunk_id
 WHERE e.model = :model AND c.knowledge_id IN (...)
 ORDER BY distance
 LIMIT :k;
```

Restricting a search to one manual is an ordinary bound `WHERE`, so `k` still
counts only eligible passages -- which matters because the agent has one tool
per manual. Each embedding row records its `model`, and search filters on it,
so one model's vectors are never scored against another's.

## Schema

One metadata, one engine, one file. `settings` joins `SQLModel.metadata`;
`settings_registry` and `engine.database.settings_db` are deleted, along with
`settings_database_path` and `add_missing_columns`.

Published-manual reference tables stay distinct from patient tables. NCP notes
are the intentional exception: one lifecycle table holds bundled examples and
locally generated drafts/finalized notes. Status and nullable ownership make
the boundary explicit—bundled examples use status `example` and have null
`person_id` and `facility_id`. Clinical sources are provenance records and
have no embeddings; NCP notes and their embeddings are stored separately.

```
reference_version          (bundle_version, applied_at)
ncp_note                   (id, person_id?, facility_id?, note_type, content,
                            status, created_at, updated_at, finalized_at?)
ncp_note_embedding         (ncp_note_id, model, dimensions, vector BLOB)
knowledge                  (title, knowledge_type, source, file_hash)
knowledge_chunk            (knowledge_id, ordinal, text)
knowledge_chunk_embedding  (knowledge_chunk_id, model, dimensions, vector BLOB)
```

Ported from `apps/server/src/server/models/sql/knowledge.py` and `ncp.py`,
swapping `pgvector.Vector` for a float32 `BLOB`, which is what
`_rank_by_similarity` already reads.

## Work

### 1. Knowledge moves on-device

The diet and nutrition-care manuals are the last thing `apps/server` could do
that the engine could not. Moving over:

* `models/sql/knowledge.py` — the three tables above.
* `agents/tools/knowledge_search_tools.py` — `get_knowledge_from_diet_manual`
  and friends. The NCP prompt already instructs the agent to call these;
  `engine.agents.ncp_agent` currently passes only `CALCULATOR_TOOLSET`, so the
  prompt references tools that do not exist.
* `controllers/knowledge/` — ingest and search.
* `pipelines/knowledge/ingestion/` — extractors and chunking.
* `repositories/knowledge_repo.py` — rewritten to score the stored BLOBs with
  sqlite-vec's `vec_distance_cosine` instead of querying pgvector.

### 2. Reference database build

`engine reference build` (CLI, not shipped behaviour):

1. create the schema in a fresh file,
2. ingest the manuals, chunk, embed with `nomic-embed-text`,
3. load the NCP corpus, embed,
4. `PRAGMA journal_mode=DELETE`, then `VACUUM`, so the artifact is one clean
   file with no `-wal`/`-shm` siblings,
5. write `reference_version`.

Produced at release time; not committed.

### 3. Ship and install

`tauri.conf.json` gains `bundle.resources: ["resources/default.db"]`. Rust
resolves it with `app.path().resolve(..., BaseDirectory::Resource)` and passes
the path to the engine in an environment variable, the same shape as the
existing `NTK_CONFIG_FILE` handling in `engine.rs`.

### 4. Restore semantics

Settings, clinical data and reference content now share a file, so
"restore from default" is destructive. Three distinct operations, only one of
which is:

1. **First run** — file missing, copy the bundle verbatim. Safe by definition.
2. **Reference refresh** — an update ships newer embeddings. `ATTACH` the
   bundle, replace *only* the six reference tables in one transaction, bump
   `reference_version`. Patient data and settings
   untouched. This runs on every update, so it must never touch anything else.
3. **Factory reset** — explicit, confirmed, loses everything.

The routine update path is 2, never 3.
