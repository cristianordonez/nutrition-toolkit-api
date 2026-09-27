//! Seam between the desktop shell and the Python `engine` package.
//!
//! Dev mode: shells out to `uv run --package engine engine ...` from the
//! workspace root. This is deliberately **not** shippable -- it needs `uv`, a
//! Python toolchain, and the source tree present on the machine, and a
//! Finder-launched `.app` gets a minimal PATH that usually cannot find `uv`.
//!
//! Before release this becomes a real Tauri sidecar: build `engine` into a
//! standalone binary with PyInstaller, name it with the target triple
//! (`engine-aarch64-apple-darwin`), declare it under `bundle.externalBin` in
//! `tauri.conf.json`, and swap the `Command` below for the shell plugin's
//! sidecar API. The frontend calls `invoke()` either way, so that swap stays
//! contained in this file.
//!
//! Every command here is declared `#[tauri::command(async)]`. A bare
//! `#[tauri::command]` runs the function *on the main thread*, and each of
//! these blocks on `Command::output()` until a Python subprocess exits --
//! seconds for a calculation, minutes for an ingest or a note. macOS renders
//! the webview out of process but still composites its frames on the host's
//! main thread, so a blocking command freezes the window: React mounts its
//! spinner, no frame is ever presented, and the busy state is gone again
//! before the UI repaints. `(async)` moves the call onto the multi-threaded
//! async runtime, which keeps the window painting while the engine works.

use std::path::PathBuf;
use std::process::Command;

use serde::Serialize;

/// One completed `engine` invocation.
#[derive(Debug, Serialize)]
pub struct EngineOutput {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

/// Workspace root, resolved from this crate's manifest directory
/// (`<root>/apps/desktop/src-tauri`, so three levels up).
///
/// Baked in at compile time, which is correct for dev mode and another reason
/// this path does not survive into a shipped bundle.
fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("crate should live at <workspace root>/apps/desktop/src-tauri")
        .to_path_buf()
}

/// Run the `engine` CLI with `args` and capture its output.
///
/// Runs from the workspace root because `logfire.configure()` discovers
/// `.logfire/` relative to the working directory, and points the engine at its
/// own `.env` explicitly -- that file is otherwise resolved against the working
/// directory too, so the documented `apps/desktop/engine/.env` would never be
/// read from here.
fn run(args: &[&str]) -> Result<EngineOutput, String> {
    let root = workspace_root();
    let mut command = Command::new("uv");
    command.current_dir(&root);

    // Only override when the documented file is actually there; otherwise leave
    // discovery alone so an existing root-level .env still works.
    let engine_env = root.join("apps/desktop/engine/.env");
    if engine_env.is_file() {
        command.env("NTK_CONFIG_FILE", &engine_env);
    }

    let output = command
        .args(["run", "--package", "engine", "engine"])
        .args(args)
        .output()
        .map_err(|error| {
            format!(
                "could not start the engine via `uv` ({error}). Dev mode needs `uv` \
                 on PATH and the workspace checked out at {}.",
                root.display()
            )
        })?;

    Ok(EngineOutput {
        stdout: String::from_utf8_lossy(&output.stdout).trim().to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        exit_code: output.status.code().unwrap_or(-1),
    })
}

/// Run the engine and parse its stdout as JSON.
///
/// Controller results print as JSON on stdout, and every other stream -- logs,
/// the Logfire banner, and Logfire's span output -- is kept on stderr so stdout
/// parses cleanly. Anything that writes to stdout on the Python side breaks
/// this, so a parse failure quotes what actually arrived rather than only
/// naming the offset.
fn run_json(args: &[&str]) -> Result<serde_json::Value, String> {
    let output = run(args)?;
    if output.exit_code != 0 {
        // stderr carries the traceback, and is what actually explains the
        // failure, so surface it rather than a bare exit code.
        let detail = if output.stderr.is_empty() {
            output.stdout.clone()
        } else {
            last_meaningful_line(&output.stderr)
        };
        return Err(format!("engine failed ({}): {detail}", output.exit_code));
    }
    serde_json::from_str(&output.stdout).map_err(|error| {
        format!(
            "could not parse engine output as JSON ({error}). stdout began: {}",
            preview(&output.stdout)
        )
    })
}

/// The opening of a stream, for error messages, capped so a whole note or a
/// long traceback cannot flood the UI. Truncates on a character boundary.
fn preview(text: &str) -> String {
    const LIMIT: usize = 200;
    if text.is_empty() {
        return "(nothing)".to_string();
    }
    let head: String = text.chars().take(LIMIT).collect();
    if head.len() < text.len() {
        format!("{head}…")
    } else {
        head
    }
}

/// The line of a Python traceback that names the failure.
///
/// Taking the last non-empty line is wrong for the errors that matter most
/// here: SQLAlchemy prints the exception first and then appends `[SQL: ...]`,
/// `[parameters: ...]` and a docs URL, so the tail of the output is a row of
/// bound values rather than anything a reader can act on. So look for the
/// exception line itself -- `package.module.SomeError: message` -- scanning
/// from the end to get the outermost of a chained traceback, and fall back to
/// the old behaviour when nothing matches.
fn last_meaningful_line(stderr: &str) -> String {
    stderr
        .lines()
        .map(str::trim)
        .filter(|line| is_exception_line(line))
        .next_back()
        .or_else(|| {
            stderr.lines().map(str::trim).rev().find(|line| {
                !line.is_empty() && !line.starts_with("(Background on this error at:")
            })
        })
        .unwrap_or(stderr)
        .to_string()
}

/// Whether a line reads as `SomeError: message`, the form Python uses to
/// report an uncaught exception.
fn is_exception_line(line: &str) -> bool {
    let Some((name, rest)) = line.split_once(": ") else {
        return false;
    };
    if rest.is_empty() || name.contains(char::is_whitespace) {
        return false;
    }
    // The bare class name, after any dotted module path.
    let class = name.rsplit('.').next().unwrap_or(name);
    class.ends_with("Error") || class.ends_with("Exception")
}

/// Report the engine's version, proving the desktop shell can reach it.
#[tauri::command(async)]
pub fn engine_version() -> Result<String, String> {
    let output = run(&["--version"])?;
    if output.exit_code != 0 {
        return Err(format!(
            "engine exited with {}: {}",
            output.exit_code, output.stderr
        ));
    }
    Ok(output.stdout)
}

/// Ingest documents from disk, returning what landed.
#[tauri::command(async)]
pub fn ingest_documents(paths: Vec<String>) -> Result<serde_json::Value, String> {
    if paths.is_empty() {
        return Err("Choose at least one file to upload.".to_string());
    }
    let mut args: Vec<&str> = vec!["document", "ingest", "--files"];
    args.extend(paths.iter().map(String::as_str));
    run_json(&args)
}

/// List every resident persisted in the local facts database.
#[tauri::command(async)]
pub fn list_persons() -> Result<serde_json::Value, String> {
    run_json(&["persons", "list"])
}

/// Summarize the local data available for one resident and identify gaps.
#[tauri::command(async)]
pub fn person_summary(person_id: i64) -> Result<serde_json::Value, String> {
    let person_id = person_id.to_string();
    run_json(&["persons", "summary", "--person-id", &person_id])
}

/// Generate a Nutrition Care Process for one resident.
///
/// `additional_context` is the reviewer's own steer for this note -- a reason
/// for the review or something to emphasise. Blank input is dropped rather
/// than passed as an empty flag, which the prompt would treat as a real but
/// contentless instruction.
#[tauri::command(async)]
pub fn generate_ncp(
    person_id: i64,
    note_type: String,
    additional_context: Option<String>,
) -> Result<serde_json::Value, String> {
    let person_id = person_id.to_string();
    let context = additional_context.unwrap_or_default();
    let context = context.trim();

    let mut args = vec![
        "ncp",
        "generate",
        "--person-id",
        &person_id,
        "--note-type",
        &note_type,
    ];
    if !context.is_empty() {
        args.extend(["--additional-context", context]);
    }
    run_json(&args)
}

/// Calculate daily nutrition needs from typed-in measurements.
#[tauri::command(async)]
pub fn calculate_energy(
    weight: f64,
    height: f64,
    age: i64,
    gender: String,
    goal: String,
    activity_level: f64,
    dialysis: bool,
    amputation: Option<f64>,
) -> Result<serde_json::Value, String> {
    let (weight, height, age) = (weight.to_string(), height.to_string(), age.to_string());
    let activity = activity_level.to_string();
    let mut args = vec![
        "calculate",
        "energy",
        "--weight",
        &weight,
        "--height",
        &height,
        "--age",
        &age,
        "--gender",
        &gender,
        "--goal",
        &goal,
        "--activity-level",
        &activity,
    ];
    if dialysis {
        args.push("--dialysis");
    }
    let amputation = amputation.map(|value| value.to_string());
    if let Some(value) = amputation.as_deref() {
        args.extend(["--amputation", value]);
    }
    run_json(&args)
}

/// List the enteral formulas this device can order.
///
/// Backs the formula picker. The engine resolves a formula by its exact
/// catalog name, so the UI must offer these names rather than let a reviewer
/// type one: several products share a brand and strength, and a partial name
/// matches more than one.
#[tauri::command(async)]
pub fn list_formulas() -> Result<serde_json::Value, String> {
    run_json(&["tubefeed", "formulas"])
}

/// Build a tube-feeding recommendation.
///
/// Returns the recommendation as text rather than JSON: the engine renders a
/// sentence meant to be pasted straight into a note, and reformatting it here
/// would only risk changing clinical wording.
#[tauri::command(async)]
pub fn calculate_tubefeed(
    kcal_low: i64,
    kcal_high: i64,
    formula: String,
    hours: Option<i64>,
    bolus: bool,
    bolus_feeds: Option<i64>,
    feeding_route: Option<String>,
) -> Result<String, String> {
    let (low, high) = (kcal_low.to_string(), kcal_high.to_string());
    let mut args = vec![
        "tubefeed",
        "calculate",
        "--energy-needs",
        &low,
        &high,
        "--formula",
        &formula,
    ];
    let hours = hours.map(|value| value.to_string());
    if let Some(value) = hours.as_deref() {
        args.extend(["--n-hours", value]);
    }
    if bolus {
        args.push("--bolus");
    }
    let feeds = bolus_feeds.map(|value| value.to_string());
    if let Some(value) = feeds.as_deref() {
        args.extend(["--n-bolus-feeds", value]);
    }
    if let Some(route) = feeding_route.as_deref().filter(|r| !r.is_empty()) {
        args.extend(["--feeding-route", route]);
    }

    let output = run(&args)?;
    if output.exit_code != 0 {
        let detail = if output.stderr.is_empty() {
            output.stdout.clone()
        } else {
            last_meaningful_line(&output.stderr)
        };
        return Err(format!("engine failed ({}): {detail}", output.exit_code));
    }
    Ok(output.stdout)
}

/// Read the device user's own settings.
#[tauri::command(async)]
pub fn get_settings() -> Result<serde_json::Value, String> {
    run_json(&["settings", "show"])
}

/// Change the device user's own settings.
///
/// `dark_mode` is a three-state string rather than a bool: "on" and "off" are
/// explicit choices and "system" follows the OS appearance, which is what a
/// device that has never visited Settings does. `None` leaves the setting
/// untouched, so this command can grow more fields without a caller that
/// omits one wiping it.
/// `cloud_api_token` is the user's own credential. It is passed straight
/// through to the engine, which puts it in the OS keychain -- it is never
/// written to the SQLite database and never read back out, so nothing downstream
/// can log it. An empty string removes the stored token.
#[tauri::command(async)]
pub fn update_settings(
    dark_mode: Option<String>,
    use_cloud_model: Option<String>,
    cloud_api_token: Option<String>,
) -> Result<serde_json::Value, String> {
    let mut args = vec!["settings", "update"];
    if let Some(mode) = dark_mode.as_deref() {
        args.extend(["--dark-mode", mode]);
    }
    if let Some(cloud) = use_cloud_model.as_deref() {
        args.extend(["--use-cloud-model", cloud]);
    }
    if let Some(token) = cloud_api_token.as_deref() {
        args.extend(["--cloud-api-token", token]);
    }
    run_json(&args)
}

/// Report whether on-device extraction is ready on this machine.
#[tauri::command(async)]
pub fn local_model_status() -> Result<serde_json::Value, String> {
    run_json(&["localmodel", "status"])
}

/// Download the on-device model if this machine does not have it yet.
///
/// Blocks for as long as the pull takes, which is minutes for a multi-gigabyte
/// model. Progress currently goes to the engine's stderr rather than back to
/// the UI; streaming it would mean emitting Tauri events from a spawned child
/// instead of capturing output in one shot.
#[tauri::command(async)]
pub fn local_model_ensure() -> Result<serde_json::Value, String> {
    run_json(&["localmodel", "ensure"])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The shape of a constraint failure: SQLAlchemy puts the bound
    /// parameters after the exception, so the tail of stderr is useless.
    #[test]
    fn exception_is_preferred_over_sqlalchemy_trailers() {
        let stderr = "Traceback (most recent call last):\n  \
             File \"repo.py\", line 9, in load\n    \
             session.commit()\n\
             sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE \
             constraint failed: clinical_fact.clinical_source_id, \
             clinical_fact.fact_type, clinical_fact.identity_hash\n\
             [SQL: INSERT INTO clinical_fact (clinical_source_id, fact_type, \
             identity_hash) VALUES (?, ?, ?)]\n\
             [parameters: (95, 'lab', 'abc123')]\n\
             (Background on this error at: https://sqlalche.me/e/20/gkpj)";

        let line = last_meaningful_line(stderr);

        assert!(line.starts_with("sqlalchemy.exc.IntegrityError:"), "got: {line}");
        assert!(line.contains("UNIQUE constraint failed"), "got: {line}");
    }

    #[test]
    fn a_plain_message_still_comes_through() {
        assert_eq!(last_meaningful_line("could not start\n"), "could not start");
    }

    #[test]
    fn a_bare_exception_line_is_found() {
        let stderr = "Traceback (most recent call last):\n\
             ValueError: A person identifier is required";
        assert_eq!(
            last_meaningful_line(stderr),
            "ValueError: A person identifier is required"
        );
    }

    #[test]
    fn workspace_root_contains_the_engine_package() {
        let root = workspace_root();
        assert!(
            root.join("apps/desktop/engine/pyproject.toml").is_file(),
            "workspace root resolved to {}, which has no engine package",
            root.display()
        );
    }

    /// Exercises the same path the frontend's `invoke("engine_version")` takes.
    /// Needs `uv` and the Python toolchain, matching dev-mode's requirements.
    #[test]
    fn engine_version_reports_a_version() {
        let version = engine_version().expect("engine should respond in dev mode");
        assert!(
            version.starts_with("engine "),
            "unexpected version output: {version}"
        );
    }

    /// Proves stdout parses as JSON, which the whole UI depends on: the engine
    /// also writes a Logfire banner and logs, and those must stay on stderr.
    #[test]
    fn list_persons_returns_parsed_json() {
        let value = list_persons().expect("persons list should respond");
        assert!(
            value.get("persons").and_then(|p| p.as_array()).is_some(),
            "expected a persons array, got: {value}"
        );
    }

    #[test]
    fn ingest_documents_rejects_an_empty_selection() {
        let error = ingest_documents(vec![]).expect_err("empty selection should fail");
        assert!(error.contains("at least one file"), "got: {error}");
    }

    #[test]
    fn person_summary_reports_a_missing_person() {
        let error = person_summary(987_654).expect_err("unknown person should fail");
        assert!(error.contains("Person 987654 was not found"), "got: {error}");
    }

    #[test]
    fn traceback_summary_skips_sqlalchemy_reference_trailer() {
        let stderr = "sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: document.checksum\n\
                      (Background on this error at: https://sqlalche.me/e/20/gkpj)";

        assert_eq!(
            last_meaningful_line(stderr),
            "sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: document.checksum"
        );
    }

    /// A missing resident must surface as an error rather than silently
    /// succeeding, since the UI renders whatever comes back.
    #[test]
    fn generate_ncp_reports_a_missing_person() {
        let error =
            generate_ncp(987_654, "quarterly".to_string(), None)
                .expect_err("unknown person should fail");
        assert!(error.contains("engine failed"), "got: {error}");
    }

    /// Whitespace-only context must not reach the model as an instruction.
    #[test]
    fn blank_context_is_not_passed_through() {
        let error = generate_ncp(
            987_654,
            "quarterly".to_string(),
            Some("   \n ".to_string()),
        )
            .expect_err("unknown person should still fail");
        assert!(
            !error.contains("--additional-context"),
            "blank context should have been dropped: {error}"
        );
    }

    /// Status has to answer even with no Ollama installed, because the panel
    /// renders on every app start regardless.
    #[test]
    fn local_model_status_describes_this_machine() {
        let value = local_model_status().expect("status should always answer");
        assert!(
            value.get("ram_gb").and_then(serde_json::Value::as_u64).is_some(),
            "expected ram_gb, got: {value}"
        );
        for key in ["supported", "ollama_running", "model_downloaded"] {
            assert!(
                value.get(key).and_then(serde_json::Value::as_bool).is_some(),
                "expected boolean {key}, got: {value}"
            );
        }
    }
}
