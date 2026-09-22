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
};

/** A generated Nutrition Care Process note. */
export type GeneratedNCP = {
  person_id: number;
  person_name: string;
  person_identifier: string;
  note_text: string;
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

export const generateNcp = (personId: number, additionalContext?: string) =>
  call<GeneratedNCP>("generate_ncp", { personId, additionalContext });

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
