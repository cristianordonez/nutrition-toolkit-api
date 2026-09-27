import { useEffect, useState } from "react";
import {
  type DarkMode,
  type SettingsView,
  getSettings,
  resolveTheme,
  updateSettings,
} from "./engine";

/**
 * Apply a stored appearance choice to the document.
 *
 * Setting `data-theme` rather than toggling a class lets the stylesheet treat
 * "no explicit choice" as its own state: the `prefers-color-scheme` media
 * query stays in charge until the attribute appears.
 */
export function applyTheme(darkMode: boolean | null): void {
  document.documentElement.setAttribute("data-theme", resolveTheme(darkMode));
}

function Switch({
  checked,
  label,
  disabled,
  onChange,
}: {
  checked: boolean;
  label: string;
  disabled: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`switch${checked ? " switch--on" : ""}`}
      disabled={disabled}
      onClick={onChange}
    >
      <span className="switch__thumb" />
    </button>
  );
}

export function SettingsPage() {
  const [view, setView] = useState<SettingsView | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState("");

  useEffect(() => {
    getSettings()
      .then(setView)
      .catch((caught: Error) => setError(caught.message));
  }, []);

  async function save(changes: Parameters<typeof updateSettings>[0]) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSettings(changes);
      setView(updated);
      applyTheme(updated.settings.dark_mode);
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const settings = view?.settings ?? null;
  const dark = settings ? resolveTheme(settings.dark_mode) === "dark" : false;
  const followingSystem = settings?.dark_mode === null;
  const busy = !view || saving;

  // What the user asked for is not always what runs: enabling the hosted model
  // without a stored token falls back on-device, and saying so plainly is the
  // point of showing the active provider rather than just the switch.
  const cloudRequested = settings?.use_cloud_model ?? false;
  const usingCloud = view?.active_provider === "openai";

  return (
    <div className="app__columns">
      <section className="panel">
        <h2 className="panel__title">Appearance</h2>

        <div className="setting">
          <div className="setting__text">
            <span className="setting__label">Dark mode</span>
            <span className="setting__hint">
              {followingSystem
                ? "Following your system appearance."
                : dark
                  ? "Always dark, whatever the system is set to."
                  : "Always light, whatever the system is set to."}
            </span>
          </div>
          <Switch
            checked={dark}
            label="Dark mode"
            disabled={busy}
            onChange={() =>
              save({ darkMode: (dark ? "off" : "on") as DarkMode })
            }
          />
        </div>

        {settings && !followingSystem && (
          <button
            type="button"
            className="linkbtn"
            disabled={busy}
            onClick={() => save({ darkMode: "system" })}
          >
            Follow system appearance instead
          </button>
        )}

        <h2 className="panel__title panel__title--spaced">AI model</h2>

        <div className="setting">
          <div className="setting__text">
            <span className="setting__label">Use a cloud model</span>
            <span className="setting__hint">
              {usingCloud
                ? "Resident data is sent to the hosted model."
                : cloudRequested
                  ? "Enabled, but no API token is stored — running on-device."
                  : "Everything runs on this device. Nothing is sent out."}
            </span>
          </div>
          <Switch
            checked={cloudRequested}
            label="Use a cloud model"
            disabled={busy}
            onChange={() =>
              save({ useCloudModel: cloudRequested ? "off" : "on" })
            }
          />
        </div>

        {cloudRequested && (
          <div className="tokenbox">
            <label className="field">
              <span className="field__label">
                Your API token
                {view?.has_cloud_token && " — one is stored"}
              </span>
              <input
                className="field__input"
                type="password"
                value={token}
                placeholder={
                  view?.has_cloud_token ? "••••••••  (replace)" : "sk-…"
                }
                autoComplete="off"
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
            <div className="tokenbox__actions">
              <button
                type="button"
                className="btn"
                disabled={busy || !token}
                onClick={() =>
                  save({ cloudApiToken: token }).then(() => setToken(""))
                }
              >
                Save token
              </button>
              {view?.has_cloud_token && (
                <button
                  type="button"
                  className="linkbtn"
                  disabled={busy}
                  onClick={() => save({ cloudApiToken: "" })}
                >
                  Remove stored token
                </button>
              )}
            </div>
          </div>
        )}

        {error && <p className="notice notice--bad">{error}</p>}
      </section>

      <section className="panel panel--note">
        <h2 className="panel__title">Where your data goes</h2>
        <p className="hint">
          Extraction and note generation run on this device by default, so a
          resident's record never leaves it. Turning on a cloud model sends
          that record to a hosted model instead, and needs your own API token.
        </p>
        <p className="hint">
          The token is kept in your operating system's keychain, not in the
          app's database. Non-secret settings and clinical data share one local
          SQLite file; the API token remains outside it.
        </p>
        {view && (
          <dl className="result">
            <dt>Running on</dt>
            <dd>{usingCloud ? "Hosted model" : "This device (Ollama)"}</dd>
          </dl>
        )}
      </section>
    </div>
  );
}
