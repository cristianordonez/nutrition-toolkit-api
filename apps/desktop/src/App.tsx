import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import {
  type IngestSummary,
  type Person,
  type PersonDataSummary,
  type NCPNoteType,
  SUPPORTED_EXTENSIONS,
  engineVersion,
  generateNcp,
  getPersonSummary,
  ingestDocuments,
  listPersons,
  supportedPaths,
} from "./engine";
import { EnergyPage, TubefeedPage } from "./Calculators";
import { type NoteResult, AssessmentsPage } from "./Assessments";
import { DocumentsPage } from "./Documents";
import { SettingsPage, applyTheme } from "./Settings";
import { getSettings } from "./engine";
import "./App.css";

const TABS = [
  { id: "documents", label: "Documents" },
  { id: "assessments", label: "Assessments" },
  { id: "energy", label: "Energy" },
  { id: "tubefeed", label: "Tube feeding" },
  { id: "settings", label: "Settings" },
] as const;

type TabId = (typeof TABS)[number]["id"];

type EngineState =
  | { status: "checking" }
  | { status: "ready"; version: string }
  | { status: "unavailable"; detail: string };

function App() {
  const [tab, setTab] = useState<TabId>("documents");
  const [engine, setEngine] = useState<EngineState>({ status: "checking" });
  const [persons, setPersons] = useState<Person[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [focusedPersonId, setFocusedPersonId] = useState<number | null>(null);
  const [personSummary, setPersonSummary] = useState<PersonDataSummary | null>(
    null,
  );
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryVersion, setSummaryVersion] = useState(0);

  const [files, setFiles] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<IngestSummary | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [results, setResults] = useState<NoteResult[]>([]);
  const [generating, setGenerating] = useState(false);
  // Context is per resident: a batch usually mixes review reasons, and one
  // shared note would put the wrong steer on every other resident.
  const [contexts, setContexts] = useState<Record<number, string>>({});
  // So is the assessment type: one batch can hold an annual for one resident
  // and a significant change for another. Residents without their own choice
  // use the default, which "Set all selected to" also updates.
  const [noteTypes, setNoteTypes] = useState<Record<number, NCPNoteType>>({});
  const [defaultNoteType, setDefaultNoteType] =
    useState<NCPNoteType>("quarterly");
  const noteTypeFor = (personId: number) =>
    noteTypes[personId] ?? defaultNoteType;

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

  // Ask the engine whether it is reachable. Exposed as a callback rather than
  // inlined in the effect because the answer can change while the window stays
  // open -- the engine is a separate process, so a failed import or a half-saved
  // file makes it unavailable and fixing that makes it available again. Without
  // a way to ask twice, the first answer is final until the app is restarted,
  // and the shell offers no reload shortcut to do that with.
  const checkEngine = useCallback(async () => {
    setEngine({ status: "checking" });
    try {
      const version = await engineVersion();
      setEngine({ status: "ready", version });
      await refreshPersons();
    } catch (error) {
      setEngine({ status: "unavailable", detail: (error as Error).message });
    }
  }, [refreshPersons]);

  useEffect(() => {
    void checkEngine();
  }, [checkEngine]);

  // Apply the stored appearance before the user visits Settings, so a device
  // set to dark opens dark. A failure here is deliberately silent: the
  // stylesheet still follows the OS, so the window is readable either way and
  // an unreachable engine is already reported by the badge.
  useEffect(() => {
    getSettings()
      .then((view) => applyTheme(view.settings.dark_mode))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let current = true;
    if (focusedPersonId === null) {
      setPersonSummary(null);
      setSummaryError(null);
      setSummaryLoading(false);
      return () => {
        current = false;
      };
    }

    setSummaryLoading(true);
    setSummaryError(null);
    getPersonSummary(focusedPersonId)
      .then((summary) => {
        if (current) setPersonSummary(summary);
      })
      .catch((error: Error) => {
        if (current) {
          setPersonSummary(null);
          setSummaryError(error.message);
        }
      })
      .finally(() => {
        if (current) setSummaryLoading(false);
      });
    return () => {
      current = false;
    };
  }, [focusedPersonId, summaryVersion]);

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
      if (accepted.length > 0) {
        setFiles(accepted);
        // Files land on the Documents page, so go there rather than leave the
        // drop looking like it did nothing.
        setTab("documents");
      }
    });
    return () => {
      void pending.then((unlisten) => unlisten());
    };
  }, []);

  function toggle(personId: number) {
    setFocusedPersonId(personId);
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(personId)) next.add(personId);
      return next;
    });
  }

  /**
   * Select or clear a specific set of residents, which the list passes in.
   *
   * It sends the residents currently visible rather than all of them, so with
   * a search active this acts on what the reviewer can see. Selecting 235
   * residents because three matched a search would be a nasty surprise.
   */
  function toggleAll(visible: Person[]) {
    const visibleIds = visible.map((person) => person.id);
    setSelected((current) => {
      const allChosen = visibleIds.every((id) => current.has(id));
      const next = new Set(current);
      for (const id of visibleIds) {
        if (allChosen) {
          next.delete(id);
        } else {
          next.add(id);
        }
      }
      return next;
    });
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
      setSummaryVersion((current) => current + 1);
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
        noteType: noteTypeFor(person.id),
        context: contexts[person.id]?.trim() || undefined,
        status: "pending",
      })),
    );

    for (const person of chosen) {
      try {
        const note = await generateNcp(
          person.id,
          noteTypeFor(person.id),
          contexts[person.id],
        );
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

  return (
    <main className="app">
      <header className="app__header">
        <h1 className="app__title">Nutrition Toolkit</h1>
        <nav className="tabs">
          {TABS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={`tab${tab === entry.id ? " tab--active" : ""}`}
              onClick={() => setTab(entry.id)}
              aria-current={tab === entry.id}
            >
              {entry.label}
            </button>
          ))}
        </nav>
        <EngineBadge engine={engine} onRetry={checkEngine} />
      </header>

      {tab === "energy" && <EnergyPage />}
      {tab === "tubefeed" && <TubefeedPage />}
      {tab === "settings" && <SettingsPage />}
      {tab === "documents" && (
        <DocumentsPage
          files={files}
          dragging={dragging}
          uploading={uploading}
          elapsed={elapsed}
          result={uploadResult}
          error={uploadError}
          residentCount={persons.length}
          onChooseFiles={chooseFiles}
          onSubmit={submitUpload}
          onReviewResidents={() => setTab("assessments")}
        />
      )}
      {tab === "assessments" && (
        <AssessmentsPage
          persons={persons}
          selected={selected}
          contexts={contexts}
          noteTypes={noteTypes}
          defaultNoteType={defaultNoteType}
          generating={generating}
          results={results}
          focusedPersonId={focusedPersonId}
          summary={personSummary}
          summaryLoading={summaryLoading}
          summaryError={summaryError}
          onToggle={toggle}
          onToggleAll={toggleAll}
          onContextChange={(personId, value) =>
            setContexts((current) => ({ ...current, [personId]: value }))
          }
          onNoteTypeChange={(personId, value) =>
            setNoteTypes((current) => ({ ...current, [personId]: value }))
          }
          onNoteTypeForAll={(value) => {
            setDefaultNoteType(value);
            setNoteTypes((current) => {
              const next = { ...current };
              for (const personId of selected) next[personId] = value;
              return next;
            });
          }}
          onGenerate={generateSelected}
          onAddDocuments={() => setTab("documents")}
        />
      )}
    </main>
  );
}

function EngineBadge({
  engine,
  onRetry,
}: {
  engine: EngineState;
  onRetry: () => void;
}) {
  if (engine.status === "checking") {
    return <span className="badge badge--pending">Starting engine…</span>;
  }
  if (engine.status === "ready") {
    return <span className="badge badge--ready">{engine.version}</span>;
  }
  // A button, not a label: this is the only way back once the engine has been
  // reported unavailable, and the reason it failed is usually already fixed by
  // the time the person reads it.
  return (
    <button
      type="button"
      className="badge badge--error badge--retry"
      title={`${engine.detail}\n\nClick to try again.`}
      onClick={onRetry}
    >
      Engine unavailable · retry
    </button>
  );
}

export default App;
