import { invoke } from "@tauri-apps/api/core";

/** A resident persisted in the local facts database. */
export type Person = {
  id: number;
  name: string;
  person_identifier: string | null;
  date_of_birth: string | null;
  sex: string | null;
};

/** What one ingestion run persisted. */
export type IngestSummary = {
  documents: number;
  facts: number;
  person_ids: number[];
  /**
   * Extractions that failed during the run.
   *
   * Extraction is fault-tolerant, so a run can return facts and still have
   * lost content. Non-zero means this document is only partly ingested: what
   * landed is real, and re-ingesting once the cause is fixed recovers the rest.
   */
  extraction_failures: number;
  /** A few of those failures, so the cause is visible without the log file. */
  failure_samples: string[];
  /**
   * Distinct failure messages `failure_samples` left out.
   *
   * Non-zero means the samples are not the whole story: other things went
   * wrong for reasons they do not name, and only the log has those.
   */
  unshown_failure_messages: number;
};

/** A generated Nutrition Care Process note. */
export type NCPNoteType =
  | "annual"
  | "quarterly"
  | "admission"
  | "significant_change";

export type GeneratedNCP = {
  person_id: number;
  person_name: string;
  person_identifier: string;
  ncp_note_id: number;
  note_type: NCPNoteType;
  note_text: string;
  status: "draft";
};

/**
 * Every engine call funnels through a Tauri command. Errors arrive as strings
 * from Rust, so normalise them into Error here rather than in each caller.
 */
async function call<T>(command: string, args?: Record<string, unknown>) {
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    throw new Error(typeof error === "string" ? error : String(error));
  }
}

export const engineVersion = () => call<string>("engine_version");

export const ingestDocuments = (paths: string[]) =>
  call<IngestSummary>("ingest_documents", { paths });

export const listPersons = () =>
  call<{ persons: Person[] }>("list_persons").then((result) => result.persons);

export type PersonSummaryField = {
  key: string;
  label: string;
  value: string | null;
};

export type PersonDataCategory = {
  key: string;
  label: string;
  count: number;
  detail: string | null;
};

export type MissingPersonData = {
  key: string;
  label: string;
  reason: string;
};

/** Concise coverage snapshot for a selected resident. */
export type PersonDataSummary = {
  person_id: number;
  name: string;
  person_identifier: string | null;
  overview: PersonSummaryField[];
  categories: PersonDataCategory[];
  missing: MissingPersonData[];
  conflicts: string[];
};

export const getPersonSummary = (personId: number) =>
  call<PersonDataSummary>("person_summary", { personId });

export const generateNcp = (
  personId: number,
  noteType: NCPNoteType,
  additionalContext?: string,
) => call<GeneratedNCP>("generate_ncp", { personId, noteType, additionalContext });

/** File types the document extractors accept. */
export const SUPPORTED_EXTENSIONS = ["pdf", "csv", "txt"] as const;

/** Keep only paths the extractors can actually read. */
export function supportedPaths(paths: string[]): string[] {
  return paths.filter((path) => {
    const extension = path.split(".").pop()?.toLowerCase();
    return (
      extension !== undefined &&
      (SUPPORTED_EXTENSIONS as readonly string[]).includes(extension)
    );
  });
}

/** On-device extraction readiness for this machine. */
export type LocalModelStatus = {
  enabled: boolean;
  ram_gb: number;
  supported: boolean;
  model: string | null;
  approximate_download_gb: number | null;
  ollama_running: boolean;
  model_downloaded: boolean;
  detail: string | null;
};

export const localModelStatus = () =>
  call<LocalModelStatus>("local_model_status");

export const localModelEnsure = () =>
  call<{ model: string; downloaded: boolean; already_present: boolean }>(
    "local_model_ensure",
  );

/** Daily nutrition needs from the shared calculator. */
export type EnergyNeeds = {
  bmi: number;
  bmi_category: string | null;
  current_weight_lb: number;
  ideal_weight_lb: number;
  adjusted_weight_lb: number;
  calculation_weight_lb: number;
  calculation_weight_kg: number;
  weight_basis: string;
  calorie_factor: { low: number; high: number };
  protein_factor: { low: number; high: number };
  fluid_factor: { low: number; high: number };
  calories_kcal_day: { low: number; high: number };
  protein_g_day: { low: number; high: number };
  fluids_ml_day: { low: number; high: number };
  mifflin_kcal_day: number;
};

export type EnergyArgs = {
  weight: number;
  height: number;
  age: number;
  gender: string;
  goal: string;
  activityLevel: number;
  dialysis: boolean;
  amputation?: number;
};

export const calculateEnergy = (args: EnergyArgs) =>
  call<{ needs: EnergyNeeds }>("calculate_energy", { ...args }).then(
    (result) => result.needs,
  );

/** One selectable enteral formula from the device's reference catalog. */
export type Formula = {
  name: string;
  brand: string;
  /** `ready_to_hang` | `carton` | `bottle` | `can`. */
  package_type: string;
  serving_size: number;
  serving_unit: string;
  kcal_per_ml: number | null;
};

export const listFormulas = () =>
  call<{ formulas: Formula[] }>("list_formulas").then(
    (result) => result.formulas,
  );

export type TubefeedArgs = {
  kcalLow: number;
  kcalHigh: number;
  formula: string;
  hours?: number;
  bolus: boolean;
  bolusFeeds?: number;
  feedingRoute?: string;
};

/** Returns the recommendation text, ready to paste into a note. */
export const calculateTubefeed = (args: TubefeedArgs) =>
  call<string>("calculate_tubefeed", { ...args });

/** How the window decides its appearance. */
export type DarkMode = "on" | "off" | "system";

/** The device user's own settings, stored in the shared application database. */
export type UserSettings = {
  id: number;
  full_name: string | null;
  credentials: string | null;
  /** true forces dark, false forces light, null follows the OS. */
  dark_mode: boolean | null;
  /** Whether a hosted model was requested. Not the same as it being in use. */
  use_cloud_model: boolean;
};

/** Settings plus state the database does not store. */
export type SettingsView = {
  settings: UserSettings;
  /** Whether a token is in the OS keychain. The token itself never leaves it. */
  has_cloud_token: boolean;
  /** The model an agent would actually use right now. */
  active_provider: "ollama" | "openai";
};

export const getSettings = () => call<SettingsView>("get_settings");

/** Fields left undefined are not changed. */
export const updateSettings = (changes: {
  darkMode?: DarkMode;
  useCloudModel?: "on" | "off";
  /** Goes straight to the OS keychain. "" removes the stored token. */
  cloudApiToken?: string;
}) => call<SettingsView>("update_settings", { ...changes });

/** The stored tri-state as the value a `data-theme` attribute needs. */
export const resolveTheme = (darkMode: boolean | null): "dark" | "light" => {
  if (darkMode !== null) return darkMode ? "dark" : "light";
  const prefersDark =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
};
