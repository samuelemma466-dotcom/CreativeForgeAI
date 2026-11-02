# Coordination — CreativeForge AI

Last reconciled: 2026-11-02 12:40 WAT

## Completion owner

| Owner | Scope | Responsibility | Status |
| --- | --- | --- | --- |
| OpenCode | Final Stage 1 acceptance, `frontend/**`, `docs/**`, `README.md`, and startup-script verification | Complete the final responsive/CRUD/local-chat acceptance pass, reconcile documentation, and record the result | Completed the Stage 1 acceptance pass on 2026-11-02 |
| Codex | Stage 1 implementation contributions through 12:01 WAT | Preserved shell, chat integration, tests, API contract and documentation | Handed off; no write scope unless a new handoff is recorded here |
| Uvicorn / Vite | Runtime only: API `127.0.0.1:8787`, frontend `127.0.0.1:5173` | Serve the current app; may be restarted by the active owner for verification | Not source owners |

The human owner's latest instruction supersedes earlier ownership entries. OpenCode completed the final
Stage 1 pass and recorded the result in `docs/FEATURE_STATUS.md`. The existing user database, media and
configuration were preserved; acceptance records were uniquely named and removed through the
application. Any further work requires a new recorded handoff.

## Handoff record

- Codex completed its frontend pass at 11:44 WAT and continued polishing the shell, chat integration,
  tests and docs through 12:01 WAT. Its work is preserved.
- The human owner assigned final Stage 1 completion to OpenCode. OpenCode preserved Codex's changes,
  fixed stage badges and CRUD refresh performance, added local-Ollama URL enforcement at the provider
  boundary, made the connection check lightweight, and completed the live acceptance pass.
- Final acceptance on 2026-11-02: 14 backend tests passed; TypeScript/production build passed; unified
  and separate startup scripts passed; project/brand CRUD persisted and was cleaned up; Ollama detected
  both installed models; real chat returned `UI_OK`; failure and responsive states were checked. See
  `docs/FEATURE_STATUS.md` for the detailed record.

## Integration contract

- Frontend: React + TypeScript + Vite. It calls the backend through `/api` and never accesses SQLite,
  secrets, or the media directory directly.
- Backend: FastAPI on `127.0.0.1:8787`; SQLite at `data/creativeforge.db`; local media under `media/`.
- Development UI: Vite on `127.0.0.1:5173`, proxying `/api` to port 8787.
- Ollama: local HTTP API at `127.0.0.1:11434`; installed models must be queried at runtime.
- Stage 1 `/api/ai/chat` uses the existing provider architecture with local Ollama as the zero-configuration
  default. A real local prompt/response is required for acceptance. Cloud credentials are not present;
  cloud failover must remain unclaimed and untested.
- `FREE_ONLY` cannot be disabled. No paid path, billing flow, model pull, or automatic paid fallback is
  allowed. Optional cloud providers remain unverified until tested with an explicitly configured free
  credential and verified current official terms.
- API error JSON includes a useful `detail` and stable `error` fields. Frontend messages preserve the
  entered prompt and identify provider/model where known.

## Change and handoff rules

1. Read `AGENTS.md`, `docs/PROJECT_SPEC.md`, and `docs/UI_UX_SPEC.md` before product changes.
2. Inspect the current source and `git status --short` before editing; do not replace working files wholesale.
3. Update this document when ownership, route contracts, ports, or implementation status materially changes.
4. Never overwrite another owner's work. The project currently has one active coding owner.
5. Before returning ownership, report changed paths, passing/failing checks, untested behavior, and known
   limitations. Resume another agent only after the human owner approves or a clear handoff is recorded.

## Current integration notes

- Existing Stage 1 app shell, project CRUD, brand CRUD, media library, settings, system status, provider
  adapters, and local SQLite schema are preserved.
- The repository previously contained stale docs that described a standard-library server, port 8000,
  a different database filename, and tests that had no source files. Those references have been
  reconciled to the actual FastAPI/Vite setup.
- `./scripts/start.sh` reuses a healthy API or starts the backend, waits for health, then runs the Vite
  frontend. The separate development scripts remain available.
- Runtime discovery (`GET /api/system/status`) includes Ollama and local-tool probing and is intentionally
  not run after every CRUD mutation. Workspace data refreshes independently so saves stay responsive.
