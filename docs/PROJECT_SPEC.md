# CreativeForge AI — Product Specification

Status: Stage 1 implementation baseline
Updated: 2026-11-02
Owner: human project owner; implementation split recorded in `docs/COORDINATION.md`

This is the consolidated product, architecture, cost and acceptance specification. It is
subordinate only to direct instructions from the human owner. `docs/UI_UX_SPEC.md` is the
authoritative interface specification, and `AGENTS.md` makes both documents mandatory for future
sessions.

---

## 1. Product vision

CreativeForge AI is a premium, local-first advertising and creative-production workspace. It helps a
small team or independent creator move from a brand and a campaign brief to strategy, copy, graphics,
video, voice, subtitles and exports without requiring a paid cloud subscription.

The product must feel like a real commercial creative suite: intentional navigation, professional
density, clear hierarchy, high-quality previews and honest state reporting. It must not be a generic
dashboard with AI buttons attached.

The core promise is:

> A complete creative workspace that still works when there is no cloud account, no API key and no
> network connection, using the computer it is installed on.

## 2. Non-negotiable constraints

### 2.1 Strictly ₦0

- The application must remain fully usable with **no cloud account, no API key and no payment method**.
- `FREE_ONLY` is enforced by the backend and cannot be disabled through the API or UI.
- Paid models, paid API calls, billing, subscriptions, trials that require a card, paid fallbacks and
  silent paid upgrades are prohibited.
- Only providers with a verified free path may be implemented: local Ollama, OpenRouter models whose
  IDs end in `:free`, Gemini free-tier text models, and Groq free-plan text models.
- Paid models must be rejected **before** a request is sent. A provider catalog failure must fail
  closed, not "try anyway".
- When free quota is exhausted, the request must stop or move to another verified free provider. It
  must never charge the user.
- Connection checks must not download models. Model downloads require an explicit human action outside
  the application and are never triggered by the app.
- No analytics, telemetry, hosted fonts, remote images, or other runtime network dependencies are
  required for the core experience.

### 2.2 Hardware limits

The reference machine is a low-resource laptop:

- Intel Core i5-2540M, 2 physical cores / 4 logical CPUs, with legacy integrated Intel graphics;
  no modern dedicated GPU was identified.
- 7.6 GiB physical RAM, about 3.8 GiB available at the latest audit, plus 15 GiB swap. Swap is not
  equivalent to physical memory.
- About 384 GiB free disk space at the latest audit.
- Ollama models verified installed on 2026-11-02: `llama3.2:3b` (2.0 GB) and `qwen2.5:1.5b`
  (986 MB). Re-check the live inventory before use; do not download models automatically.

Therefore:

- Prefer small text models (1.5B–3B parameters). Do not make a 7B+ model a requirement.
- Run at most one local AI request at a time; the backend serialises Ollama calls.
- Keep default responses short enough to complete on CPU. Long generation is an explicit user choice.
- Use lightweight previews and generate full-resolution output as a separate, cancellable job.
- Avoid large frontend dependencies, heavy animation, and unnecessary image decoding.
- The UI must stay responsive while a model is running; AI work happens off the main interaction path.
- All core operations must degrade with a clear error when Ollama or a media tool is unavailable.

### 2.3 Honesty

- A screen is not complete because it renders. The function it promises must work.
- No invented projects, campaigns, revenue, engagement, customers, testimonials, analytics or
  notifications. Counts must come from SQLite.
- Unfinished workspaces must be visibly marked and must not pretend to generate content.
- AI output is a draft until the user edits and saves it. It must not overwrite user work silently.
- Cloud failover cannot be claimed as verified until it is exercised with the user's own free key.
- Distinguish deterministic templates and compositions from generated imagery.

## 3. Users and jobs

Primary user: a solo founder, marketer or creative professional who wants agency-style output without a
subscription.

Core jobs:

1. Capture a brand's facts, voice, audience, colours and guidelines once.
2. Create a project for a campaign or creative deliverable.
3. Turn a brief into a strategy, angles, headlines, scripts, captions and a storyboard.
4. Compose a graphic and export a real image.
5. Build a short video on a timeline and export a real MP4.
6. Generate a local voiceover and subtitles.
7. Review, manage and reuse exported work.
8. Ask a contextual assistant for help inside the active workspace.

## 4. Scope by stage

### Stage 1 — Application foundation (complete and accepted 2026-11-02)

Required, complete and verified:

- Premium responsive application shell and navigation.
- Professional dashboard with real stored state and useful empty states.
- FastAPI backend, React + TypeScript frontend, SQLite persistence.
- Project create, list, open, save, update and delete.
- Brand profile create, edit, list and delete.
- Brand Kit workspace.
- Media Library with safe local uploads and previews.
- Settings workspace with local Ollama URL/model detection, system status and FREE_ONLY reporting.
- Local AI assistant with real chat through installed Ollama models, with no cloud credentials or
  cloud fallback required for Stage 1.
- Real loading, error, success and empty states.
- Start scripts, README, regression tests and API contract.

Stage 1 is a foundation, not the full creative suite. Campaigns, Creative Studio, Video Studio and
Exports are marked as upcoming workspaces and must not be presented as finished.

### Stage 2 — Campaigns and copy

- Guided campaign brief with progress indicator and preserved input.
- Local strategy generation with structured strategy output.
- Editable strategy, audience, angles, headlines, scripts, captions and storyboard.
- Copy rewrite, shorten, expand, tone change and platform variations.
- Save, regenerate and delete campaign content.
- Contextual assistant actions on selected copy.

### Stage 3 — Creative Studio

- Real design canvas with selectable, movable, resizable layers.
- Images, text and shapes; brand assets, templates and layers.
- Position, size, typography, colour, opacity, alignment and layer controls.
- Undo/redo, save state, aspect-ratio previews.
- Deterministic server-side image rendering and export with actual file output.

### Stage 4 — Video Studio and Exports

- Desktop-style editor: media bin, preview, inspector, multi-track timeline, playhead, zoom.
- Video, image, text, audio and subtitle tracks with visibility/lock controls.
- Lightweight preview separate from full render.
- Persisted timeline state and undo/redo.
- Background render jobs with real progress, cancellation, output validation and error recovery.
- Export presets, aspect ratio, resolution, frame rate, quality, audio and destination.
- Completed export details: filename, format, size, location, playback and re-export.
- Simplified review experience on small screens.

### Stage 5 — Voice and subtitles

- Offline voice generation with eSpeak NG, selectable voice/rate/pitch, real audio output.
- Editable SRT generation, import and styling, downloadable subtitle files.

### Stage 6 — Optional free cloud providers

- Free-tier adapters only after official terms are re-verified and recorded.
- Explicit key entry, backend-only secret storage, clear provider/model status.
- Quota/rate-limit cooldowns and automatic fallback that never includes a paid model.
- No cloud key is required for any core workflow.

### Cross-workspace functional requirements

These requirements define the complete product target across the stages above. A feature remains
unimplemented until its real operation, persistence, error handling, and export path work.

**Brand Kit:** support multiple profiles with business description, industry, products/services, target
audience, voice, colors, logo, contact details, website, social links, preferred advertising platforms,
and brand guidelines. Campaign and creative AI must use the selected profile as context. Missing brand
facts must not be invented.

**Campaign Studio:** capture campaign name, brand, product/service, target customer, objective,
platform, duration, optional budget, offer, customer problem, call to action, and creative instructions.
Generate an editable strategy, positioning, customer pains, value proposition, USP, angles, concepts,
recommendations, content calendar, headlines, hooks, short/long scripts, captions, landing-page copy,
promotional messages, email copy, narration, and storyboard. Support professional, luxury,
conversational, emotional, persuasive, bold, playful, and corporate tones, plus regenerate, rewrite,
expand, shorten, tone change, and save actions.

**Creative Studio:** import/organize source media and brand assets; crop/resize, add text and text
effects, shapes, overlays, opacity, filters, layout changes and layers; apply colors and logos; and export
a real image. Provide reusable social-ad, product-promotion, sale, event, business, poster, story, Reels
cover, YouTube thumbnail, and landscape-banner layouts in 1:1, 4:5, 9:16, and 16:9. A deterministic
template or composition must never be called newly AI-generated imagery. Image generation is an
optional provider capability only after a working free model/service and its terms are verified.

**Video Studio:** import and preview video, images, and audio; trim, split, reorder and remove clips;
add text/titles/lower-thirds, subtitles, music and voice; control volume and fades; add basic transitions,
pan/zoom and image motion; and set aspect ratio and output resolution. The timeline should support video,
image, text/graphic, voice, music, and subtitle tracks. Persist a validated project representation, use
undo/redo where practical, and separate lightweight previews from final FFmpeg render jobs. Natural
language edits must become a validated structured plan, be shown before application, then map only to
approved FFmpeg operations. Never execute arbitrary model-generated commands. Preserve source media.

**Voice and subtitles:** start with offline eSpeak NG TTS; import and preview audio, control volume and
fades, mix voice/music, and place voice in the timeline. Support manual subtitle timing/editing, SRT
import/export, positioning/styling, and optional subtitle burn-in. Automatic transcription is optional
until an offline recognizer is tested on the reference CPU.

**Export Centre:** support TikTok, Instagram Reels/Feed/Stories, Facebook Feed/Stories, YouTube Shorts,
YouTube landscape, and general landscape presets. Let users configure resolution, frame rate, bitrate or
quality, container, and audio settings. Report actual render progress and claim success only after the
output exists and FFprobe validates it. Show the real filename, format, file size, location, preview or
playback, and export-again action.

**Hybrid AI:** keep provider interfaces independent for text, image, video, speech, and transcription.
Expose provider/model/capabilities/pricing category/availability/limits/configuration/error state. Keep
credentials out of frontend JavaScript and logs. Tell users which provider handled a request. Reject
paid models before dispatch; honor free quotas; on exhaustion stop or move only to another independently
verified free path; never silently upgrade.

## 5. Technical architecture

```text
Browser: React 18 + TypeScript + Vite
   │  /api (Vite proxy in development)
   ▼
FastAPI on 127.0.0.1:8787
   ├── SQLite data/creativeforge.db
   ├── media/uploads, projects, previews, voice, exports
   ├── Ollama on 127.0.0.1:11434
   ├── optional verified free cloud providers (backend-only keys)
   ├── Pillow (graphic rendering)
   ├── FFmpeg / FFprobe (video, audio, thumbnails)
   └── eSpeak NG (offline voice)
```

- Frontend: single-page app, typed API client, no direct database or filesystem access.
- Backend: router modules by domain, Pydantic validation, SQLite migrations via `schema_migrations`
  and `PRAGMA user_version` compatibility.
- Media: generated storage names, signature validation, size caps, path containment, content served by
  media ID. The media directory is not exposed as a static server.
- Process safety: FFmpeg and other tools invoked with argument arrays; AI-generated code and arbitrary
  user-supplied FFmpeg commands are never executed.
- Ports: API `127.0.0.1:8787`; Vite `127.0.0.1:5173`. Port 8000 belongs to another project.
- Storage defaults: database `data/creativeforge.db`, media under `media/`, secrets under
  `data/secrets.json` (backend only, never returned raw).

### 5.1 Provider chain

For future optional cloud use, `FREE_ONLY` selection order may be configured as:

1. Selected free cloud provider (only if configured and verified).
2. Other configured free clouds in the saved priority order.
3. Local Ollama.

Selecting Ollama skips cloud providers entirely. Paid models are rejected before dispatch. Cloud
quota/rate-limit errors create a cooldown and the chain may continue to another configured free
option. If every free option fails, the response explains what failed and confirms that no paid
fallback was attempted. No cloud provider has been tested with credentials for this project, so
cloud failover remains unverified.

### 5.2 AI assistant

The Stage 1 assistant:

- Uses local Ollama by default and works without cloud credentials. Stage 1 acceptance must exercise
  a real installed local model. Do not claim cloud failover is tested without real credentials.
- Receives the active project and/or brand context from SQLite, not from client-invented facts.
- Accepts conversation history, an optional selected-text payload and a mode
  (`chat`, `critique`, `ideas`, `rewrite`).
- Returns the provider, model, local/cloud processing flag, duration, token counts and chain attempts.
- Never writes to project or brand records. Applying a suggestion is always an explicit user action.

## 6. Data model (current)

- `brands`: name, description, industry, products, audience, voice, colours, logo, contact, website,
  socials, platforms, guidelines, timestamps.
- `projects`: type (`general`, `design`, `video`), name, description, status, brand, campaign, JSON data,
  thumbnail, timestamps.
- `campaigns`: brief fields, status, strategy JSON, generated timestamp.
- `copy_items`: campaign/brand links, kind, tone, title, content.
- `media`: original name, stored name, relative path, MIME type, kind, size, dimensions/duration.
- `exports`: project, type, format, status, progress, output path, settings, probe result, error.
- `subtitles`: project, title, SRT, style.
- `ai_usage`: provider, model, operation, token counts, duration, timestamp.
- `settings`: key/value local preferences (Ollama endpoint/model, provider priority, theme).

Deleting a brand keeps projects and clears their brand link. Deleting a project preserves its exported
files. Schema changes require a new additive migration; never destroy user data.

## 7. UX requirements

The full interface specification is `docs/UI_UX_SPEC.md`. Key requirements:

- Dark premium identity: `#080808` canvas, `#101010` sidebar, `#161616` surfaces, `#292929` borders,
  `#F2F0EB` primary text, `#A1A1AA` secondary text, `#C7FF2F` accent.
- Space Grotesk headings, Inter body text, JetBrains Mono metadata. All fonts must be local-first; no
  runtime font CDN dependency.
- Lucide icons, consistent tokens, restrained accent use, subtle motion, reduced-motion support.
- Required sidebar destinations: Overview, Campaigns, Creative Studio, Video Studio, Brand Kit, Media
  Library, Exports, Settings. Projects remain reachable as a first-class workspace utility.
- Every interactive element performs a real action or is clearly disabled/labelled unfinished.
- Real empty, loading, error and success states; confirm destructive actions; protect unsaved work.
- Desktop-first editing surfaces; mobile support for dashboard, campaigns, brand management, media,
  project review and the assistant.
- Test at 1440, 1280, 1024 and 390 px; no horizontal page overflow; keyboard focus and semantic labels.

## 8. Security and privacy

- Bind services to localhost by default.
- No account required; workspace data stays in the local database and media folders.
- Never send secrets to the frontend or logs. API keys are stored backend-side only.
- Validate every request body, file type, file size and identifier.
- Prevent path traversal and arbitrary command execution.
- Do not expose the media directory as static files.
- AI output is untrusted text: never execute it, never treat it as shell/FFmpeg input.
- Cloud use is opt-in by adding a free key; the UI must state when processing is local vs cloud.

## 9. Stage 1 acceptance tests

A Stage 1 build is accepted only when all of the following are demonstrated:

1. `./scripts/start.sh` starts/reuses the API on `127.0.0.1:8787` and starts the UI on
   `127.0.0.1:5173` without silently installing dependencies.
2. `./scripts/dev-backend.sh` and `./scripts/dev-frontend.sh` also start each service separately.
3. The UI loads live backend data without console/network errors.
4. A project can be created, seen after reload, edited and deleted in SQLite.
5. A brand can be created, edited, listed and deleted.
6. Ollama is detected, and its installed models are listed without downloading one.
7. A real prompt sent through the CreativeForge assistant returns a real local model response.
8. Chat displays provider, model, local/cloud status, loading state and actionable errors.
9. The app works with no cloud key. Paid models and remote Ollama URLs are rejected.
10. Empty, error and success states are visible and accurate.
11. `pytest`, TypeScript typecheck and production build pass.
12. The interface is inspected at 1440, 1280, 1024 and 390 px.

## 10. Definition of done

A feature is done only when:

- its real backend operation exists and is validated;
- its frontend is wired to that operation;
- loading, empty, error and success states exist;
- it works without a cloud key;
- it is tested, documented, and never claims more than it does.
