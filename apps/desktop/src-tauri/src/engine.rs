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
/// Controller results print as JSON on stdout; logging and the Logfire banner
/// go to stderr, so stdout parses cleanly on its own.
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
    serde_json::from_str(&output.stdout)
        .map_err(|error| format!("could not parse engine output as JSON ({error})"))
}

/// The last non-empty, non-indented line, which for a Python traceback is the
/// exception itself rather than the frames above it.
fn last_meaningful_line(stderr: &str) -> String {
    stderr
        .lines()
        .rev()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .unwrap_or(stderr)
        .to_string()
}

/// Report the engine's version, proving the desktop shell can reach it.
#[tauri::command]
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
#[tauri::command]
pub fn ingest_documents(paths: Vec<String>) -> Result<serde_json::Value, String> {
    if paths.is_empty() {
        return Err("Choose at least one file to upload.".to_string());
    }
    let mut args: Vec<&str> = vec!["document", "ingest", "--files"];
    args.extend(paths.iter().map(String::as_str));
    run_json(&args)
}

/// List every resident persisted in the local facts database.
#[tauri::command]
pub fn list_persons() -> Result<serde_json::Value, String> {
    run_json(&["persons", "list"])
}

/// Generate a Nutrition Care Process for one resident via cloud-api.
#[tauri::command]
pub fn generate_ncp(person_id: i64) -> Result<serde_json::Value, String> {
    let person_id = person_id.to_string();
    run_json(&["ncp", "generate", "--person-id", &person_id])
}

/// Report whether on-device extraction is ready on this machine.
#[tauri::command]
pub fn local_model_status() -> Result<serde_json::Value, String> {
    run_json(&["localmodel", "status"])
}

/// Download the on-device model if this machine does not have it yet.
///
/// Blocks for as long as the pull takes, which is minutes for a multi-gigabyte
/// model. Progress currently goes to the engine's stderr rather than back to
/// the UI; streaming it would mean emitting Tauri events from a spawned child
/// instead of capturing output in one shot.
#[tauri::command]
pub fn local_model_ensure() -> Result<serde_json::Value, String> {
    run_json(&["localmodel", "ensure"])
}

#[cfg(test)]
mod tests {
    use super::*;

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

    /// A missing resident must surface as an error rather than silently
    /// succeeding, since the UI renders whatever comes back.
    #[test]
    fn generate_ncp_reports_a_missing_person() {
        let error = generate_ncp(987_654).expect_err("unknown person should fail");
        assert!(error.contains("engine failed"), "got: {error}");
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
