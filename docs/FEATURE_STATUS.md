# Feature status

Updated: 2026-11-02

## Stage 1 implemented

- FastAPI backend and React/TypeScript/Vite frontend on loopback with a same-origin `/api` proxy.
- Versioned SQLite schema at `data/creativeforge.db`; media under `media/`.
- Premium responsive shell with Overview, Projects, Campaigns, Creative Studio, Video Studio, Brand Kit,
  Media Library, Exports, and Settings navigation. Later-stage destinations clearly identify themselves
  as not implemented.
- Overview counts, storage and recent projects come from the local application data; empty states are
  shown when there is no content.
- Project list, create, detail/edit, status update, delete, and brand association.
- Brand profile create, list, edit, delete, and project unlink behavior.
- Validated media upload, metadata list, and content preview through a media ID. Original uploads are
  kept intact.
- Settings for local Ollama URL/model, connection test, installed-model list, theme, system/tool status,
  and read-only FREE_ONLY state.
- Contextual assistant endpoint and UI. It accepts project/brand context and chat, critique, ideas, and
  rewrite modes. The assistant reports provider/model, local/cloud processing, duration, and fallback
  status. It never saves or applies output automatically.
- Local Ollama generation calls are serialized for the laptop's limited CPU/RAM. Selecting Ollama uses
  only Ollama; local failure does not fall through to a cloud provider.
- Startup scripts and project documentation, including API contract and coordination ownership.

## Verification state

This section records the final Stage 1 checks. Automated backend tests use a temporary database, so
they do not alter `data/creativeforge.db`.

- Backend regression tests: **14 passed** on 2026-11-02 (`./scripts/test-backend.sh`), including remote
  Ollama URL rejection and a connection check that lists installed models without generating text.
- Frontend TypeScript/production build: **passed** on 2026-11-02
  (`npm --prefix frontend run build`).
- Startup: `./scripts/start.sh` started both services from a clean stop (API ready after 4 s, Vite
  after 2 s). `./scripts/dev-backend.sh` and `./scripts/dev-frontend.sh` also started their services
  separately and returned HTTP 200.
- Live SQLite CRUD on isolated Chromium: a project was created, edited, confirmed after reload and
  deleted; a brand was created, edited, listed and deleted. Acceptance records were removed and the
  workspace returned to zero projects and zero brands.
- Media Library: a real PNG was uploaded through the UI, listed, previewed from its validated media ID
  and deleted through the API. The original file was preserved and the pre-existing library asset was
  untouched.
- Ollama detection listed `llama3.2:3b` and `qwen2.5:1.5b` without downloading anything. The settings
  connection check completed in about **0.39 s** in the UI (**0.15 s** through the API) and does not
  load a model.
- Real local chat through the assistant returned **`UI_OK`** from `llama3.2:3b` with project and brand
  context. The UI showed `LOCAL`, the provider/model and duration. The observed request time ranged
  from **4.3 s warm** to **135.7 s cold** on this CPU.
- Failure state: an unreachable local URL produced an actionable HTTP 502 chain error stating that no
  paid fallback was attempted, with retry and provider-settings actions. The local URL was restored to
  `http://127.0.0.1:11434` afterward.
- Remote Ollama URLs are rejected with HTTP 422 before any request is sent.
- Responsive checks at **1440, 1280, 1024 and 390 px** showed no document horizontal overflow. At
  390 px the assistant drawer filled the viewport and its bubbles stayed inside the drawer.
- Browser console errors: **0**; uncaught exceptions: **0**; failed network requests: **0**. The
  intentional failure check produced one expected HTTP 502 from `/api/ai/chat`.
- Cloud adapters and cloud failover: **not tested**; no credentials are configured and no cloud path is
  claimed as verified.
- The one pre-existing media asset in `media/` was left untouched; it was not created by this
  acceptance run.

## Not implemented

- Campaign brief and strategy generation, content calendar, editable copy library.
- Interactive graphic canvas and image composition/export.
- Timeline-based video editing and final video render/export.
- Voiceover production, subtitle editing/transcription, and audio mixing.
- AI-generated image or video generation.
- Persistent conversations or a project revision history/undo system.
- Verified cloud provider failover.

## Known limitations

- Local inference is CPU-bound and can be slow: a cold `llama3.2:3b` response took about 2.2 minutes
  during acceptance, while a warm response completed in a few seconds. Response time depends on the
  installed model, prompt length and system load.
- Assistant conversations stay in the current browser tab and are not persisted to SQLite.
- The settings connection check verifies the local server and installed models only. Real inference is
  exercised by sending an assistant message.
- Cloud adapters exist in backend code but are not verified with credentials or accepted as Stage 1
  functionality; current official free-tier terms have not been verified for this handoff.
- Python's Starlette test client emits an HTTPX deprecation warning; the test suite currently passes.
