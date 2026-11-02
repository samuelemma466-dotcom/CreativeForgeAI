# Implementation checklist

## Stage 0 — environment audit

- [x] Inspect the existing repository and preserve its application, database, media, and installed
  dependencies.
- [x] Record Node, npm, Python, backend package, media-tool, storage, memory, CPU/GPU, and Ollama status.
- [x] Query the existing Ollama models; do not download any models.
- [x] Record service ports, paths, and persistent engineering/cost rules.

## Stage 1 — application foundation

- [x] FastAPI + Pydantic backend, React + TypeScript + Vite frontend, and versioned SQLite.
- [x] Premium responsive shell, dashboard, navigation, real empty states, and unfinished-stage labels.
- [x] Project CRUD and brand CRUD, including editing of the complete brand profile.
- [x] Local settings, Ollama connection/model detection, system status, and enforced FREE_ONLY state.
- [x] Real contextual Ollama chat route and provider/model, loading, success, error, retry, and rewrite UI.
- [x] Local media library with safe upload/preview paths and preservation of originals.
- [x] Project/API contract, authoritative product/UI specs, coordination, README, and non-installing start
  scripts.
- [x] Final isolated backend suite, frontend typecheck and production build.
- [x] Live application API CRUD checked against the real SQLite database and test records cleaned up.
- [x] Real prompt/response checked through the running UI using installed local Ollama.
- [x] Chromium screenshots and interaction/overflow checks at 1440, 1280, 1024, and 390 px.
- [x] Final startup and acceptance run recorded in `FEATURE_STATUS.md`.

Stage 1 acceptance completed on 2026-11-02. Cloud adapters remain unverified and are not required for
Stage 1; do not describe cloud failover as tested until an owner-supplied free credential is configured
and a real request succeeds.

## Later stages — not started

- [ ] Stage 2: campaign briefs, local strategy generation, editable copy and saved campaign workflow.
- [ ] Stage 3: interactive design canvas, brand assets/templates, and actual image export.
- [ ] Stage 4: structured timeline editor, lightweight preview, safe FFmpeg render jobs, and exports.
- [ ] Stage 5: offline voiceover, audio mixing, subtitle editing, and SRT workflows.
- [ ] Stage 6: optional cloud adapters only after official free access terms and a real request are
  verified.
- [ ] Stage 7: cross-stage history, final polish, and expanded quality assurance.

Do not begin Stage 2 until every remaining Stage 1 item is complete or explicitly reported as blocked.
