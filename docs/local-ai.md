# AI providers

Nutrition Toolkit supports exactly two AI providers. The user chooses one in
Settings:

| Provider | Where it runs | Default |
| -------- | ------------- | ------- |
| **Local AI** | a llama.cpp server (`llama-server`) on this machine, reached over localhost | yes |
| **OpenAI** | OpenAI's hosted API, with the user's own API token | no |

There is no automatic fallback. If the selected provider fails, the app
reports the error and stops. It never sends the request to the other provider.

## Architecture

```text
ExtractionAgent ──┐
NCP (note) agent ─┼──> AIController ──┬──> LocalAIProvider ──HTTP──> llama-server ──> GGUF
ai check / eval ──┘                   └──> OpenAIProvider ────HTTP──> OpenAI
```

* **`engine.services.ai.controller.AIController`** is the only place a provider
  is chosen, from the user's `settings.ai_provider`. Agents ask it for a
  pydantic-ai `Model` (`model()`), or use `chat()` for a single request without
  tools. They never learn which provider answered.
* **`LocalAIProvider`** (`services/ai/local_provider.py`) only knows a URL. It
  doesn't care whether llama-server was started by hand, by a test, or (later)
  by the desktop app.
* **`OpenAIProvider`** (`services/ai/openai_provider.py`) reads the user's token
  from the OS keychain. If no token is stored, it raises
  `OpenAIConfigurationError`.
* **`ProviderErrorBoundary`** (`services/ai/boundary.py`) wraps both providers.
  It turns timeouts, refused connections and HTTP errors into
  `LocalAI*Error` / `OpenAI*Error` with messages a user can read, and never
  includes a prompt or response.

**Structured output.** An agent declares a Pydantic output type, and each
provider handles it its own way:

* **Local AI** sends it as a `response_format` JSON schema, which llama-server
  compiles into a grammar so the model can only produce valid JSON.
  `LocalJsonSchemaTransformer` marks each union's `type` tag as required, so the
  grammar always emits it.
* **OpenAI** uses its own structured output.

pydantic-ai validates the result either way. Agents contain no
provider-specific code.

## Running Local AI in development

The engine never starts, stops or configures llama-server. Run it yourself;
the native build uses Metal on Apple Silicon:

```bash
brew install llama.cpp
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
```

The engine uses `http://127.0.0.1:8080` by default. To use another port or an
API key:

```bash
export NUTRITION_AI_LLAMA_URL=http://127.0.0.1:9090
export NUTRITION_AI_LLAMA_API_KEY=...   # only if the server was started with --api-key
```

Or put the same lines in the engine's `.env`.

Then start the app (`cd apps/desktop && npm run tauri dev`) or use the CLI
from the repository root:

```bash
uv run --package engine engine ai status                 # {"provider": "local", "status": "ready"}
uv run --package engine engine ai check --structured     # tiny non-clinical probe via AIController
```

Pick a model sized for the machine. A 7B–14B instruct model (Q4_K_M) is
realistic for clinical extraction. A 0.5B model is enough to prove the wiring
but invents and misses facts.

Docker is not used for development: Docker on macOS has no Metal GPU, and its
default memory is too small for a 14B model.

## Switching providers

In **Settings → AI model**, choose Local AI or OpenAI. From the CLI:

```bash
uv run --package engine engine settings update --ai-provider local    # or openai
```

OpenAI needs your own API token, saved from Settings (it goes to the OS
keychain). With OpenAI selected and no token stored, requests fail with
"OpenAI is selected but no API token is stored." The app does not switch
providers on its own.

## Environment variables

| Variable | Meaning |
| -------- | ------- |
| `NUTRITION_AI_LLAMA_URL` | llama-server base URL (default `http://127.0.0.1:8080`) |
| `NUTRITION_AI_LLAMA_API_KEY` | Sent as a bearer token when the server was started with `--api-key` |
| `NUTRITION_AI_TEMPERATURE`, `NUTRITION_AI_MAX_TOKENS` | Default sampling settings for Local AI |
| `NUTRITION_AI_REQUEST_TIMEOUT_SECONDS` | Per-request timeout (default 600). Requests are never retried |

These are read in one place: `LocalAISettings` in `engine.models.settings`.

## Security and privacy

* **Local only.** Local AI accepts only loopback URLs (`127.0.0.1`,
  `localhost`, `::1`); anything else is refused.
* **Nothing clinical in logs or errors.** Logs and errors never contain
  prompts, clinical text, resident names or model output. Logs record only
  operational events, such as "Local AI request completed in 4.2 seconds" or
  "Local AI health check failed".
* **No content in traces.** Agent tracing runs with `include_content=False`.
* **Nothing sensitive in status.** `ai status` returns only
  `{provider, status, error}`: no URL, key, path, prompt or response.

## Testing

```bash
uv run pytest apps/desktop/engine/tests
```

This needs no model: HTTP is mocked. One opt-in live test runs against a
real server:

```bash
NUTRITION_AI_LLAMA_URL=http://127.0.0.1:8080 \
  uv run pytest apps/desktop/engine/tests/integration/test_local_ai_live.py
```

## Remaining production work

In a shipped app, the desktop runtime (Tauri) will own llama-server: locating
the bundled executable, choosing a localhost port, starting and stopping it,
and installing the GGUF model. It will then give the engine the URL, and the
same `LocalAIProvider` will use it unchanged. The sidecar build scripts
(`apps/desktop/scripts/build-llama-server.sh`/`.ps1`) and
`src-tauri/tauri.local-ai.conf.json` are kept for that work. Nothing launches
llama-server yet.
