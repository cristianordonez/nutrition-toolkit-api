import { type IngestSummary, SUPPORTED_EXTENSIONS } from "./engine";

/**
 * Bringing documents into the device: choosing files, ingesting them, and the
 * extraction settings that decide how.
 *
 * Split from assessments because the two are different sittings. Ingesting is
 * occasional and batch-shaped -- drop a stack of reports, wait minutes. Writing
 * an assessment is per resident and needs their record in view. Sharing one
 * screen meant the resident list and the note output competed with a dropzone
 * and a progress bar that were irrelevant to whichever task was in hand.
 */
export function DocumentsPage({
  files,
  dragging,
  uploading,
  elapsed,
  result,
  error,
  residentCount,
  onChooseFiles,
  onSubmit,
  onReviewResidents,
}: {
  files: string[];
  dragging: boolean;
  uploading: boolean;
  elapsed: number;
  result: IngestSummary | null;
  error: string | null;
  residentCount: number;
  onChooseFiles: () => void;
  onSubmit: (event: React.FormEvent) => void;
  onReviewResidents: () => void;
}) {
  return (
    <div className="app__columns">
      <section className="panel">
        <h2 className="panel__title">Upload documents</h2>
        <form className="upload" onSubmit={onSubmit}>
          <div
            className={`dropzone${dragging ? " dropzone--active" : ""}`}
            onClick={onChooseFiles}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") onChooseFiles();
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

        {result && (
          // Extraction is fault-tolerant, so a run that returns facts can
          // still have lost content. Colour the whole result by whether
          // anything failed, rather than reporting a cheerful count beside a
          // silent loss.
          <div
            className={`notice notice--${
              result.extraction_failures > 0 ? "warn" : "ok"
            }`}
          >
            <p className="notice__line">
              {result.documents} document
              {result.documents === 1 ? "" : "s"}, {result.facts} fact
              {result.facts === 1 ? "" : "s"} across{" "}
              {result.person_ids.length} resident
              {result.person_ids.length === 1 ? "" : "s"}.
            </p>

            {result.extraction_failures > 0 && (
              <>
                <p className="notice__line notice__line--strong">
                  {result.extraction_failures} extraction
                  {result.extraction_failures === 1 ? "" : "s"} failed — this
                  document is only partly ingested.
                </p>
                <ul className="notice__list">
                  {result.failure_samples.map((sample) => (
                    <li key={sample}>{sample}</li>
                  ))}
                  {/* Three samples describe a run that failed one way. On a run
                      that failed several ways they are misleading on their own,
                      so say what is missing rather than letting the reader
                      assume these are every cause. */}
                  {result.unshown_failure_messages > 0 && (
                    <li className="notice__more">
                      and {result.unshown_failure_messages} other message
                      {result.unshown_failure_messages === 1 ? "" : "s"} not
                      shown — see the log for the rest.
                    </li>
                  )}
                </ul>
                <p className="notice__line">
                  Fix the cause, then ingest the same files again to recover
                  what is missing.
                </p>
              </>
            )}

            {/* The next step after ingesting is almost always writing a note,
                and that now lives on another page. */}
            <button type="button" className="linkbtn" onClick={onReviewResidents}>
              Review residents →
            </button>
          </div>
        )}
        {error && <p className="notice notice--bad">{error}</p>}
      </section>

      <section className="panel panel--note">
        <h2 className="panel__title">Extraction</h2>
        <p className="hint">
          Documents are read by the AI provider chosen in Settings.{" "}
          {residentCount} resident{residentCount === 1 ? "" : "s"} on file.
        </p>
      </section>
    </div>
  );
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}
