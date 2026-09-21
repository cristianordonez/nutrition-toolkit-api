import { useCallback, useEffect, useState } from "react";
import {
  type LocalModelStatus,
  localModelEnsure,
  localModelStatus,
} from "./engine";

/**
 * On-device extraction status, checked once on app start.
 *
 * Downloading is gated on local extraction being enabled: the model is
 * multiple gigabytes, so enabling it is the consent, not app launch. When it
 * is off we only report what this machine could run.
 */
export function LocalModelPanel() {
  const [status, setStatus] = useState<LocalModelStatus | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      return setStatus(await localModelStatus());
    } catch (caught) {
      return setError((caught as Error).message);
    }
  }, []);

  const download = useCallback(async () => {
    setDownloading(true);
    setError(null);
    try {
      await localModelEnsure();
      await refresh();
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setDownloading(false);
    }
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Auto-pull on start only once the user has opted in and the daemon is up.
  useEffect(() => {
    if (
      status?.enabled &&
      status.supported &&
      status.ollama_running &&
      !status.model_downloaded &&
      !downloading
    ) {
      void download();
    }
  }, [status, downloading, download]);

  if (!status) {
    return <p className="hint">Checking on-device model…</p>;
  }

  return (
    <div className="local">
      <p className="local__line">
        <span className="local__label">Extraction</span>
        <span>{status.enabled ? "on-device" : "hosted (OpenAI)"}</span>
      </p>
      <p className="local__line">
        <span className="local__label">This machine</span>
        <span>{status.ram_gb} GB</span>
      </p>

      {!status.supported ? (
        <p className="notice notice--bad">{status.detail}</p>
      ) : (
        <>
          <p className="local__line">
            <span className="local__label">Model</span>
            <span>{status.model}</span>
          </p>
          {!status.ollama_running ? (
            <p className="notice notice--bad">
              Ollama isn’t running. Install it from ollama.com, then reopen this
              app.
            </p>
          ) : status.model_downloaded ? (
            <p className="notice notice--ok">Model downloaded and ready.</p>
          ) : (
            <button
              type="button"
              className="btn"
              onClick={() => void download()}
              disabled={downloading}
            >
              {downloading
                ? "Downloading…"
                : `Download (~${status.approximate_download_gb} GB)`}
            </button>
          )}
          {downloading && (
            <p className="hint">
              This takes several minutes. Progress is in the engine log.
            </p>
          )}
        </>
      )}
      {error && <p className="notice notice--bad">{error}</p>}
    </div>
  );
}
