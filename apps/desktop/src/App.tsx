import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  type GeneratedNCP,
  type IngestSummary,
  type Person,
  engineVersion,
  generateNcp,
  ingestDocuments,
  listPersons,
} from "./engine";
import { LocalModelPanel } from "./LocalModelPanel";
import "./App.css";

type EngineState =
  | { status: "checking" }
  | { status: "ready"; version: string }
  | { status: "unavailable"; detail: string };

function App() {
  const [engine, setEngine] = useState<EngineState>({ status: "checking" });
  const [persons, setPersons] = useState<Person[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [files, setFiles] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<IngestSummary | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [note, setNote] = useState<GeneratedNCP | null>(null);
  const [generating, setGenerating] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);

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

  async function generate(personId: number) {
    setSelectedId(personId);
    setGenerating(true);
    setNote(null);
    setNoteError(null);
    try {
      setNote(await generateNcp(personId));
    } catch (error) {
      setNoteError((error as Error).message);
    } finally {
      setGenerating(false);
    }
  }

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
            <button type="button" className="btn" onClick={chooseFiles}>
              Choose files…
            </button>

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
            >
              {uploading ? "Ingesting…" : `Ingest ${files.length || ""}`.trim()}
            </button>
          </form>

          {uploading && (
            <p className="hint">
              Extraction runs per document and can take a while.
            </p>
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

          <h2 className="panel__title panel__title--spaced">
            On-device extraction
          </h2>
          <LocalModelPanel />

          <h2 className="panel__title panel__title--spaced">
            Residents{persons.length > 0 && ` (${persons.length})`}
          </h2>
          {persons.length === 0 ? (
            <p className="hint">No residents yet — ingest a document first.</p>
          ) : (
            <ul className="residents">
              {persons.map((person) => (
                <li key={person.id}>
                  <button
                    type="button"
                    className={`resident${
                      selectedId === person.id ? " resident--active" : ""
                    }`}
                    onClick={() => generate(person.id)}
                    disabled={generating}
                  >
                    <span className="resident__name">{person.name}</span>
                    {person.person_identifier && (
                      <span className="resident__id">
                        {person.person_identifier}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel panel--note">
          <h2 className="panel__title">Nutrition Care Process note</h2>
          {generating && <p className="hint">Generating…</p>}
          {noteError && <p className="notice notice--bad">{noteError}</p>}
          {!generating && !noteError && !note && (
            <p className="hint">Select a resident to generate a note.</p>
          )}
          {note && <pre className="note">{note.note_text}</pre>}
        </section>
      </div>
    </main>
  );
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
