# Architecture

## Runtime topology

```text
React 18 + TypeScript + Vite (127.0.0.1:5173)
       │ typed JSON /api requests through the Vite proxy
       ▼
FastAPI + Pydantic (127.0.0.1:8787)
       ├── SQLite: data/creativeforge.db
       ├── local media roots: media/{uploads,projects,previews,voice,exports}
       ├── Ollama HTTP API: 127.0.0.1:11434
       └── optional provider adapters (not verified for Stage 1)
```

The frontend has no direct database or filesystem access. Uploaded bytes are written and served by the
backend through validated media IDs. Both app servers bind to localhost by default. Port 8000 belongs
to another local project and is not used here.

## Frontend

- `frontend/src/App.tsx`: application shell, navigation, dashboard, projects, Brand Kit, Media Library,
  Settings, and the contextual assistant drawer.
- `frontend/src/api.ts`: typed `/api` request functions and useful HTTP error extraction.
- `frontend/src/types.ts`: API entities and request/response types.
- `frontend/src/styles.css`: local design tokens, responsive layouts, focus and reduced-motion states.
- `frontend/vite.config.ts`: development server on port 5173 and API proxy to port 8787.

The 8 required navigation destinations are present. Stage 1 workspaces are functional; campaigns,
graphic design, video editing, and exports are labelled as upcoming rather than represented as working
features. Projects remain a first-class workspace utility. The assistant is available from the top bar
and project/dashboard actions.

## Backend

- `backend/app/main.py`: FastAPI lifecycle, CORS allowlist, API routes, validation/provider error JSON,
  and built frontend serving when `frontend/dist` exists.
- `backend/app/config.py`: local paths, service ports, tool names, and local Ollama defaults.
- `backend/app/db.py`: SQLite connections and additive, versioned schema migrations.
- `backend/app/schemas.py`: Pydantic input validation and bounds.
- `backend/app/routers/`: domain endpoints for dashboard/system, settings/providers, chat, projects,
  brands, media, campaigns/copy, design/video, voice/subtitles, and exports.
- `backend/app/services/providers.py`: provider interface, local Ollama adapter, free-only selection,
  local inference serialization, health/cooldown records, and optional cloud adapters.
- `backend/app/services/media.py`: filename-independent storage, media validation and safe media ID
  lookup.
- `backend/app/services/video_render.py`, `design_render.py`, `tts.py`: later-stage media services;
  their existence does not mean their workspaces are accepted for Stage 1.

Use argument arrays for subprocess calls. Never concatenate user input into shell commands or execute
AI-generated commands. Never expose secret values through frontend payloads or logs.

## Stage 1 request flows

### Project and brand persistence

The client calls `/api/projects` and `/api/brands`. FastAPI validates identifiers and request fields;
the route uses parameterized SQL and SQLite transactions. Brand deletion leaves projects intact and
clears their optional brand link. Project deletion does not remove media or completed exports.

### Contextual local AI

The client sends the current message history, optional project/brand IDs, selected copy (rewrite mode),
and task mode to `POST /api/ai/chat`. The backend loads the linked facts from SQLite, bounds context
and conversation size, and calls the existing provider abstraction. With local Ollama selected, the
chain contains only `ollama`; an Ollama error does not trigger cloud fallback. The Ollama semaphore
allows one generation at a time on this low-memory CPU. The settings connection check inspects the
local server and installed model list only; real inference is exercised by sending a chat message.
Local provider calls reject remote Ollama hosts before making a request. The response includes the
provider/model, local/cloud indicator, duration/token metadata, context summary, and attempts. AI output
is not saved automatically. Usage is logged in SQLite without secrets.

Cloud adapters and their provider-specific limits are not verified with credentials for this project.
Do not claim they work or that current free quotas are sufficient. See `FREE_PROVIDER_POLICY.md`.

## Data and storage

SQLite defaults to `data/creativeforge.db`; media defaults to `media/`. Runtime paths can be set for
isolated testing with `CFAI_DATA_DIR`, `CFAI_MEDIA_DIR`, `CFAI_DB_PATH`, `CFAI_SECRETS_PATH`, and
`CFAI_TEMP_DIR`. Tests set these before importing FastAPI and remove their temporary workspace at
process exit.

Core tables include brands, projects, campaigns, copy items, media, exports, subtitles, settings,
schema migration metadata, and AI usage. Schema changes must be additive and versioned. Never delete
or replace the user's database to test a migration.

## Provider and cost boundaries

- Default text path: local Ollama with an already-installed model.
- Model detection calls the local tags endpoint; it never pulls a model.
- `FREE_ONLY` is always true and rejected if a caller tries to turn it off.
- Paid models are rejected before provider dispatch by the existing provider policy.
- Ollama URLs must resolve to allowed local HTTP hosts.
- Cloud adapters/credentials are optional and not tested; selecting Ollama does not use them.
- No payment information, billing operation, or paid fallback is implemented.

## Security boundaries

- The API and Vite development server bind to loopback by default.
- CORS is restricted to local frontend origins.
- Uploads have size/type/signature validation and unique generated storage names.
- The media root is not mounted as an unrestricted static directory.
- Secrets remain backend-only; APIs expose configuration booleans, not key material.
- User and model content is treated as data and is never executed.
- FFmpeg and other subprocess calls use argument arrays and validated project structures.
