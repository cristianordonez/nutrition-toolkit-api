import { useMemo, useState } from "react";

import type {
  GeneratedNCP,
  NCPNoteType,
  Person,
  PersonDataSummary,
} from "./engine";
import { PatientSummary } from "./PatientSummary";

/** Assessment types a note can be written as, in the order offered. */
export const NOTE_TYPE_OPTIONS: { value: NCPNoteType; label: string }[] = [
  { value: "annual", label: "Annual" },
  { value: "quarterly", label: "Quarterly" },
  { value: "admission", label: "Admission" },
  { value: "significant_change", label: "Significant change" },
  { value: "wound", label: "Wound" },
  { value: "follow_up", label: "Follow up" },
];

const noteTypeLabel = (value: NCPNoteType) =>
  NOTE_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? value;

/** One resident's generation outcome, kept so a failure does not hide others. */
export type NoteResult = {
  person: Person;
  noteType: NCPNoteType;
  context?: string;
} & (
  | { status: "pending" }
  | { status: "done"; note: GeneratedNCP }
  | { status: "failed"; detail: string }
);

/**
 * Choosing residents, reading what is on file for them, and writing notes.
 *
 * The resident's own record sits beside the note being written for them, which
 * is the comparison the reviewer actually makes. Ingestion lives on its own
 * page so a dropzone and a progress bar are not competing for that space.
 */
export function AssessmentsPage({
  persons,
  selected,
  contexts,
  noteTypes,
  defaultNoteType,
  generating,
  results,
  focusedPersonId,
  summary,
  summaryLoading,
  summaryError,
  onToggle,
  onToggleAll,
  onContextChange,
  onNoteTypeChange,
  onNoteTypeForAll,
  onGenerate,
  onAddDocuments,
}: {
  persons: Person[];
  selected: Set<number>;
  contexts: Record<number, string>;
  /** Each selected resident's assessment type; unset means the default. */
  noteTypes: Record<number, NCPNoteType>;
  defaultNoteType: NCPNoteType;
  generating: boolean;
  results: NoteResult[];
  focusedPersonId: number | null;
  summary: PersonDataSummary | null;
  summaryLoading: boolean;
  summaryError: string | null;
  onToggle: (personId: number) => void;
  onToggleAll: (visible: Person[]) => void;
  onContextChange: (personId: number, value: string) => void;
  onNoteTypeChange: (personId: number, value: NCPNoteType) => void;
  onNoteTypeForAll: (value: NCPNoteType) => void;
  onGenerate: () => void;
  onAddDocuments: () => void;
}) {
  const done = results.filter((entry) => entry.status !== "pending").length;

  const [query, setQuery] = useState("");
  const visible = useMemo(() => matching(persons, query), [persons, query]);
  // A resident selected before searching stays selected, so say so rather than
  // let the count disagree with the list for no visible reason.
  const hiddenSelected = selected.size - visible.filter(isIn(selected)).length;
  const allVisibleChosen =
    visible.length > 0 && visible.every((person) => selected.has(person.id));
  const typeOf = (personId: number) => noteTypes[personId] ?? defaultNoteType;
  // The "all" control shows a type only when every selected resident has it;
  // otherwise it reads "Mixed" rather than claiming one type for the batch.
  const selectedTypes = new Set([...selected].map(typeOf));
  const sharedType =
    selectedTypes.size === 1 ? [...selectedTypes][0] : undefined;

  return (
    <div className="app__columns">
      <section className="panel">
        <div className="panel__heading">
          <h2 className="panel__title">
            Residents
            {persons.length > 0 &&
              (query
                ? ` (${visible.length} of ${persons.length})`
                : ` (${persons.length})`)}
          </h2>
          {visible.length > 0 && (
            <button
              type="button"
              className="linkbtn"
              onClick={() => onToggleAll(visible)}
            >
              {allVisibleChosen ? "Clear" : "Select all"}
            </button>
          )}
        </div>

        {persons.length > 0 && (
          <div className="search">
            <input
              type="search"
              className="field__input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search name or ID"
              aria-label="Search residents"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}

        {selected.size > 0 && hiddenSelected > 0 && (
          <p className="hint">
            {hiddenSelected} selected resident
            {hiddenSelected === 1 ? " is" : "s are"} hidden by this search.
          </p>
        )}

        {persons.length === 0 ? (
          <p className="hint">
            No residents yet.{" "}
            <button type="button" className="linkbtn" onClick={onAddDocuments}>
              Ingest a document
            </button>{" "}
            to get started.
          </p>
        ) : visible.length === 0 ? (
          <p className="hint">
            No resident matches “{query}”.{" "}
            <button type="button" className="linkbtn" onClick={() => setQuery("")}>
              Clear search
            </button>
          </p>
        ) : (
          <ul className="residents">
            {visible.map((person) => (
              <li key={person.id}>
                <label
                  className={`resident${
                    focusedPersonId === person.id ? " resident--active" : ""
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(person.id)}
                    onChange={() => onToggle(person.id)}
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
                  <div className="resident__options">
                    <select
                      className="resident__type"
                      value={typeOf(person.id)}
                      onChange={(event) =>
                        onNoteTypeChange(
                          person.id,
                          event.target.value as NCPNoteType,
                        )
                      }
                      aria-label={`Assessment type for ${person.name}`}
                      disabled={generating}
                    >
                      {NOTE_TYPE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      className="resident__context"
                      value={contexts[person.id] ?? ""}
                      onChange={(event) =>
                        onContextChange(person.id, event.target.value)
                      }
                      placeholder="Context for this note (optional)"
                      aria-label={`Context for ${person.name}`}
                      disabled={generating}
                    />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {persons.length > 0 && (
          <>
            <label className="field">
              <span className="field__label">Set all selected to</span>
              <select
                className="field__input"
                value={selected.size === 0 ? defaultNoteType : (sharedType ?? "")}
                onChange={(event) =>
                  onNoteTypeForAll(event.target.value as NCPNoteType)
                }
                disabled={generating}
              >
                {selected.size > 0 && sharedType === undefined && (
                  <option value="" disabled>
                    Mixed
                  </option>
                )}
                {NOTE_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn btn--primary btn--block"
              onClick={onGenerate}
              disabled={selected.size === 0 || generating}
            >
              {generating
                ? `Generating ${done + 1} of ${results.length}…`
                : `Generate ${selected.size || ""} note${
                    selected.size === 1 ? "" : "s"
                  }`.replace("  ", " ")}
            </button>
          </>
        )}
      </section>

      <section className="panel panel--note">
        <PatientSummary
          summary={summary}
          loading={summaryLoading}
          error={summaryError}
        />

        <h2 className="panel__title panel__title--spaced">
          Notes{results.length > 0 && ` (${done}/${results.length})`}
        </h2>
        {results.length === 0 ? (
          <p className="hint">Select one or more residents, then generate.</p>
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
              <p className="noteblock__context">
                {noteTypeLabel(entry.noteType)} assessment
              </p>
              {entry.context && (
                <p className="noteblock__context">Context: {entry.context}</p>
              )}
              {entry.status === "pending" && <p className="hint">Waiting…</p>}
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
  );
}

/**
 * Residents whose name or identifier contains every word of the query.
 *
 * Matching each word separately rather than the whole string lets "cai en14"
 * find "Cai, Test (EN140472)" -- the name and the identifier are shown
 * together, so searching across both is what the list looks like it does.
 */
function matching(persons: Person[], query: string): Person[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return persons;
  return persons.filter((person) => {
    const haystack =
      `${person.name} ${person.person_identifier ?? ""}`.toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

/** Predicate for counting how many of a list are already selected. */
function isIn(selected: Set<number>) {
  return (person: Person) => selected.has(person.id);
}
