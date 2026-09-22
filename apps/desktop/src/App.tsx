import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import {
  type GeneratedNCP,
  type IngestSummary,
  type Person,
  SUPPORTED_EXTENSIONS,
  engineVersion,
  generateNcp,
  ingestDocuments,
  listPersons,
  supportedPaths,
} from "./engine";
import { LocalModelPanel } from "./LocalModelPanel";
import "./App.css";

type EngineState =
  | { status: "checking" }
  | { status: "ready"; version: string }
  | { status: "unavailable"; detail: string };

/** One resident's generation outcome, kept so a failure does not hide others. */
type NoteResult = { person: Person; context?: string } & (
  | { status: "pending" }
  | { status: "done"; note: GeneratedNCP }
  | { status: "failed"; detail: string }
);

function App() {
  const [engine, setEngine] = useState<EngineState>({ status: "checking" });
  const [persons, setPersons] = useState<Person[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const [files, setFiles] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<IngestSummary | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [results, setResults] = useState<NoteResult[]>([]);
  const [generating, setGenerating] = useState(false);
  // Context is per resident: a batch usually mixes review reasons, and one
  // shared note would put the wrong steer on every other resident.
  const [contexts, setContexts] = useState<Record<number, string>>({});

  const [elapsed, setElapsed] = useState(0);

  const [dragging, setDragging] = useState(false);
  // The drop handler runs outside React's render, so it reads the latest
  // uploading state through a ref rather than a stale closure.
  const uploadingRef = useRef(false);
  uploadingRef.current = uploading;

  const refreshPersons = useCallback(async () => {
    try {
      setPersons(await listPersons());
    } catch (error) {
      setUploadError((error as Error).message);
    }
  }, []);

  useEffect(() => {
    engineVersion()
      .then((version) => {
        setEngine({ status: "ready", version });
        return refreshPersons();
      })
      .catch((error: Error) =>
        setEngine({ status: "unavailable", detail: error.message }),
      );
  }, [refreshPersons]);

  // Ingestion returns only when every document is done, so there is no real
  // progress to report -- elapsed time is the honest signal that work is
  // still happening.
  useEffect(() => {
    if (!uploading) return undefined;
    setElapsed(0);
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsed(Math.round((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [uploading]);

  /**
   * Tauri intercepts native drag-and-drop, so HTML5 drop events never fire in
   * the webview. Its own event is also the only one that carries real
   * filesystem paths, which is what the engine needs.
   */
  useEffect(() => {
    const pending = getCurrentWebview().onDragDropEvent((event) => {
      if (event.payload.type === "enter" || event.payload.type === "over") {
        if (!uploadingRef.current) setDragging(true);
        return;
      }
      setDragging(false);
      if (event.payload.type !== "drop" || uploadingRef.current) return;

      const accepted = supportedPaths(event.payload.paths);
      const rejected = event.payload.paths.length - accepted.length;
      setUploadResult(null);
      setUploadError(
        rejected > 0
          ? `Ignored ${rejected} file${rejected === 1 ? "" : "s"} — only ${SUPPORTED_EXTENSIONS.join(", ")} are supported.`
          : null,
      );
      if (accepted.length > 0) setFiles(accepted);
    });
    return () => {
      void pending.then((unlisten) => unlisten());
    };
  }, []);

  function toggle(personId: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(personId)) next.add(personId);
      return next;
    });
  }

  function toggleAll() {
    setSelected((current) =>
      current.size === persons.length
        ? new Set()
        : new Set(persons.map((person) => person.id)),
    );
  }

  async function chooseFiles() {
    const chosen = await open({
      multiple: true,
      filters: [{ name: "Documents", extensions: ["pdf", "csv", "txt"] }],
    });
    if (!chosen) return;
    setFiles(Array.isArray(chosen) ? chosen : [chosen]);
    setUploadError(null);
    setUploadResult(null);
  }

  async function submitUpload(event: React.FormEvent) {
    event.preventDefault();
    if (files.length === 0 || uploading) return;
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const summary = await ingestDocuments(files);
      setUploadResult(summary);
      setFiles([]);
      await refreshPersons();
    } catch (error) {
      setUploadError((error as Error).message);
    } finally {
      setUploading(false);
    }
  }

  /**
   * Generate one resident at a time. Notes are long model calls, and running
   * them together would make a failure hard to attribute and hammer the API;
   * each result lands as it finishes so a bad one never hides the rest.
   */
  async function generateSelected() {
    const chosen = persons.filter((person) => selected.has(person.id));
    if (chosen.length === 0 || generating) return;
    setGenerating(true);
    setResults(
      chosen.map((person) => ({
        person,
        context: contexts[person.id]?.trim() || undefined,
        status: "pending",
      })),
    );

    for (const person of chosen) {
      try {
        const note = await generateNcp(person.id, contexts[person.id]);
        setResults((current) =>
          current.map((entry) =>
            entry.person.id === person.id
              ? { ...entry, status: "done", note }
              : entry,
          ),
        );
      } catch (error) {
        const detail = (error as Error).message;
        setResults((current) =>
          current.map((entry) =>
            entry.person.id === person.id
              ? { ...entry, status: "failed", detail }
              : entry,
          ),
        );
      }
    }
    setGenerating(false);
  }

  const done = results.filter((entry) => entry.status !== "pending").length;

  return (
    <main className="app">
      <header className="app__header">
        <h1 className="app__title">Nutrition Toolkit</h1>
        <EngineBadge engine={engine} />
      </header>

      <div className="app__columns">
        <section className="panel">
          <h2 className="panel__title">Upload documents</h2>
          <form className="upload" onSubmit={submitUpload}>
            <div
              className={`dropzone${dragging ? " dropzone--active" : ""}`}
              onClick={chooseFiles}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") chooseFiles();
              }}
            >
              <span className="dropzone__label">
                {dragging ? "Drop to add" : "Drop files here"}
              </span>
              <span className="dropzone__hint">
                or click to browse · {SUPPORTED_EXTENSIONS.join(", ")}
              </span>
            </div>

            {files.length > 0 && (
              <ul className="filelist">
                {files.map((path) => (
                  <li key={path} className="filelist__item" title={path}>
                    {path.split("/").pop()}
                  </li>
                ))}
              </ul>
            )}

            <button
              type="submit"
              className="btn btn--primary"
              disabled={files.length === 0 || uploading}
              aria-busy={uploading}
            >
              {uploading
                ? "Ingesting…"
                : `Ingest${files.length ? ` ${files.length}` : ""}`}
            </button>
          </form>

          {uploading && (
            <div className="progress" role="status" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              <span className="progress__text">
                Extracting {files.length} document
                {files.length === 1 ? "" : "s"}…
                <span className="progress__elapsed">{formatElapsed(elapsed)}</span>
              </span>
            </div>
          )}
          {uploadResult && (
            <p className="notice notice--ok">
              {uploadResult.documents} document
              {uploadResult.documents === 1 ? "" : "s"}, {uploadResult.facts}{" "}
              fact
              {uploadResult.facts === 1 ? "" : "s"} across{" "}
              {uploadResult.person_ids.length} resident
              {uploadResult.person_ids.length === 1 ? "" : "s"}.
            </p>
          )}
          {uploadError && <p className="notice notice--bad">{uploadError}</p>}

          <div className="panel__heading panel__title--spaced">
            <h2 className="panel__title">
              Residents{persons.length > 0 && ` (${persons.length})`}
            </h2>
            {persons.length > 0 && (
              <button type="button" className="linkbtn" onClick={toggleAll}>
                {selected.size === persons.length ? "Clear" : "Select all"}
              </button>
            )}
          </div>

          {persons.length === 0 ? (
            <p className="hint">No residents yet — ingest a document first.</p>
          ) : (
            <ul className="residents">
              {persons.map((person) => (
                <li key={person.id}>
                  <label className="resident">
                    <input
                      type="checkbox"
                      checked={selected.has(person.id)}
                      onChange={() => toggle(person.id)}
                      disabled={generating}
                    />
                    <span className="resident__name">{person.name}</span>
                    {person.person_identifier && (
                      <span className="resident__id">
                        {person.person_identifier}
                      </span>
                    )}
                  </label>
                  {selected.has(person.id) && (
                    <input
                      type="text"
                      className="resident__context"
                      value={contexts[person.id] ?? ""}
                      onChange={(event) =>
                        setContexts((current) => ({
                          ...current,
                          [person.id]: event.target.value,
                        }))
                      }
                      placeholder="Context for this note (optional)"
                      aria-label={`Context for ${person.name}`}
                      disabled={generating}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={generateSelected}
            disabled={selected.size === 0 || generating}
          >
            {generating
              ? `Generating ${done + 1} of ${results.length}…`
              : `Generate ${selected.size || ""} note${
                  selected.size === 1 ? "" : "s"
                }`.replace("  ", " ")}
          </button>

          <h2 className="panel__title panel__title--spaced">
            On-device extraction
          </h2>
          <LocalModelPanel />
        </section>

        <section className="panel panel--note">
          <h2 className="panel__title">
            Notes{results.length > 0 && ` (${done}/${results.length})`}
          </h2>
          {results.length === 0 ? (
            <p className="hint">
              Select one or more residents, then generate.
            </p>
          ) : (
            results.map((entry) => (
              <article key={entry.person.id} className="noteblock">
                <h3 className="noteblock__name">
                  {entry.person.name}
                  {entry.person.person_identifier && (
                    <span className="resident__id">
                      {entry.person.person_identifier}
                    </span>
                  )}
                </h3>
                {entry.context && (
                  <p className="noteblock__context">Context: {entry.context}</p>
                )}
                {entry.status === "pending" && (
                  <p className="hint">Waiting…</p>
                )}
                {entry.status === "failed" && (
                  <p className="notice notice--bad">{entry.detail}</p>
                )}
                {entry.status === "done" && (
                  <pre className="note">{entry.note.note_text}</pre>
                )}
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

function EngineBadge({ engine }: { engine: EngineState }) {
  if (engine.status === "checking") {
    return <span className="badge badge--pending">Starting engine…</span>;
  }
  if (engine.status === "ready") {
    return <span className="badge badge--ready">{engine.version}</span>;
  }
  return (
    <span className="badge badge--error" title={engine.detail}>
      Engine unavailable
    </span>
  );
}

export default App;
