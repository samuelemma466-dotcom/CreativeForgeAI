# CreativeForge AI — Agent Instructions

These instructions are mandatory for every coding session, including future Codex and OpenCode
sessions.

## Authoritative documents

Read these before changing the product:

1. `docs/PROJECT_SPEC.md` — consolidated product, architecture, cost, hardware and acceptance rules.
2. `docs/UI_UX_SPEC.md` — authoritative interface, workspace, interaction, responsive and accessibility
   rules.
3. `docs/API_CONTRACT.md` — the HTTP contract shared by frontend and backend.
4. `docs/COORDINATION.md` — current ownership, handoffs and integration notes.

If documents disagree, `docs/PROJECT_SPEC.md` wins on product/architecture/cost and
`docs/UI_UX_SPEC.md` wins on interface design. Record material conflicts in `docs/COORDINATION.md`.

## Non-negotiable product rules

### Strictly ₦0

- The application must remain usable with no cloud account, no API key and no payment method.
- Keep `FREE_ONLY` enabled and enforced by the backend. It cannot be disabled through the API or UI.
- Never add paid providers, paid models, billing, subscriptions, card-required trials, paid fallbacks or
  silent paid upgrades.
- Allowed online paths are only verified free tiers: OpenRouter models ending in `:free`, Gemini
  free-tier text models, and Groq free-plan text models. Local Ollama is the default.
- No cloud path is verified for the current project handoff. Keep cloud adapters unclaimed and unused
  in Stage 1 unless official terms are checked and a real request succeeds with an owner-configured key.
- Reject paid models before sending a request. Fail closed when a free catalog cannot be verified.
- When free quota is exhausted, cool down or stop. Never charge the user and never fall through to a
  paid model.
- Never download models automatically. Connection checks only inspect what is installed.
- Core UI must not require remote fonts, images, analytics or telemetry.

### Low-resource hardware

Reference machine: Intel i5-2540M (2 physical cores / 4 logical CPUs), 7.6 GiB RAM, 15 GiB swap,
legacy integrated graphics, and no assumed dedicated GPU. The latest inventory found
`llama3.2:3b` and `qwen2.5:1.5b`; query Ollama each run before relying on them. Swap is not physical
memory.

- Prefer 1.5B–3B text models. Do not make 7B+ models a requirement.
- Serialise local AI calls; do not run multiple Ollama generations at once.
- Keep default prompts and responses short enough for CPU inference.
- Use lightweight previews and separate full-resolution renders into cancellable background jobs.
- Avoid heavy frontend dependencies and continuous animations.

### Honesty

- Do not claim a feature works until the real operation has been implemented and verified end to end.
- Never show fake metrics, projects, activity, notifications, testimonials, engagement or export
  success. Counts must come from SQLite.
- Mark unfinished workspaces clearly; do not present planned tools as working.
- AI output is a draft. Never overwrite user work without explicit authorization.
- Distinguish deterministic templates/compositions from newly generated imagery.
- Cloud failover is not "verified" until exercised with the user's own free key; say so.

## Architecture

- `frontend/` is the React 18, TypeScript and Vite client. It talks only to `/api`.
- `backend/` is the FastAPI service, SQLite persistence and media/tool integration.
- `media/` holds uploads, project files, previews, voice output and exports. Never delete original uploads
  during editing.
- `data/` holds `creativeforge.db` and backend-only secrets. Schema changes use additive migrations in
  `backend/app/db.py`; never destroy user data.
- API: `127.0.0.1:8787`. Vite: `127.0.0.1:5173`. Port 8000 belongs to another project.
- The browser never accesses SQLite or the media directory. Media is served by validated media ID.
- Invoke FFmpeg and other tools with argument arrays, never shell-interpolated input. Never execute
  AI-generated code or arbitrary FFmpeg commands.
- Keep provider integrations behind small provider modules. Free-provider selection, cooldowns and
  failover live in `backend/app/services/providers.py`.
- Bind services to localhost, keep CORS to the local frontend, and never expose or log secrets.

## Stage status

- **Stage 1 (complete and accepted on 2026-11-02):** premium shell, dashboard, projects, Brand Kit,
  Media Library, Settings, Ollama detection, and a working local AI assistant. The acceptance record is
  in `docs/FEATURE_STATUS.md`.
- **Stage 2 (not started):** campaign brief, strategy generation, editable campaign workspace and copy
  tools.
- **Stage 3:** real graphic design canvas and image export.
- **Stage 4:** multi-track video editor, render queue and export workspace.
- **Stage 5:** offline voice and subtitle workflows.
- **Stage 6:** optional free cloud adapters, only after re-verifying official terms.

Do not jump ahead and build a later stage poorly while its prerequisites are incomplete. Do not claim
cloud failover as verified without an owner-supplied free credential and a real successful request.

## UI/UX rules

- Follow `docs/UI_UX_SPEC.md` exactly for tokens, typography, shell, workspace layouts, interaction,
  motion, responsive behaviour and accessibility. Do not substitute a generic dashboard pattern.
- Use CSS variables for colours, spacing, radii and typography. Do not scatter hardcoded values.
- Required sidebar destinations: Overview, Campaigns, Creative Studio, Video Studio, Brand Kit, Media
  Library, Exports, Settings. Projects remains a first-class workspace utility.
- Every visible control must perform a real action or be clearly disabled and labelled unfinished.
- Provide real loading, error, success and empty states. Confirm destructive actions. Protect unsaved work.
- Use Lucide icons and local-first fonts. Space Grotesk and Inter are not installed on this machine;
  use the documented local fallbacks or vendor open-licensed files. Do not require a font CDN.
- Test at 1440, 1280, 1024 and 390 px. No horizontal overflow on ordinary pages.
- Support keyboard focus, semantic controls, reduced motion, and status that is not colour-only.
- Build UI and backend functionality together. A screen is not complete because it renders.

## Current ownership and coordination

- OpenCode completed the final Stage 1 acceptance pass on 2026-11-02, including `frontend/**`,
  `docs/**`, `README.md` and startup-script verification. The result is recorded in
  `docs/FEATURE_STATUS.md`.
- Codex's Stage 1 implementation through 12:01 WAT is preserved. Codex has no active write scope for
  this completion unless the human owner records a new handoff in `docs/COORDINATION.md`.
- The existing Uvicorn and Vite processes are runtime services only. They may be restarted to test
  changes, but do not treat them as source owners.
- The human owner may reassign ownership at any time. Their latest explicit instruction wins.
- Before delegating or opening another coding session, agree on directory ownership and record the
  handoff and integration contract in `docs/COORDINATION.md`.

## Engineering conventions

- Inspect current code before modifying it and preserve working user changes.
- Keep frontend and backend responsibilities separate and use typed API payloads.
- Persist user edits in SQLite or project files.
- Keep user-facing controls connected to real behaviour; hide or mark unfinished work clearly.
- Add focused tests for important backend behaviour and run relevant checks after changes.
- Update `README.md`, `docs/ARCHITECTURE.md`, `docs/FEATURE_STATUS.md`, `docs/FREE_PROVIDER_POLICY.md`,
  `docs/API_CONTRACT.md` and `docs/PROJECT_SPEC.md` as the product changes.
- Prefer small, reviewable changes. Do not install unnecessary packages, download large AI models or
  install system packages without a concrete need.

## Required checks before handoff

Backend:

```bash
./scripts/test-backend.sh
```

Frontend:

```bash
cd frontend && npm run build
```

Live checks:

- Start both services with `./scripts/start.sh` or the two dev scripts.
- Verify project and brand CRUD against SQLite.
- Verify Ollama detection and a real prompt/response through the assistant.
- Verify that the app works with no cloud key and that paid models/non-local Ollama URLs are rejected.
- Inspect the interface at 1440, 1280, 1024 and 390 px.

## Definition of done

A feature is done only when its real backend operation exists, its frontend is wired to it, loading,
empty, error and success states exist, it works without a cloud key, it is tested, and the docs describe
exactly what it does.
