# CreativeForge AI — UI/UX Design Specification

## 1. Design objective

CreativeForge AI is a premium creative-production application combining a simple SaaS experience, an organized marketing workspace, precise graphic design controls, and professional video editing. Screens must be designed around the work users perform, with clear hierarchy, consistent interactions, and real functionality. A generic dashboard with AI controls attached is not sufficient.

## 2. Visual identity

### Color tokens

| Token | Value | Use |
| --- | --- | --- |
| Main background | `#080808` | Application canvas |
| Secondary background | `#101010` | Sidebar and secondary surfaces |
| Elevated surface | `#161616` | Panels and dialogs |
| Border | `#292929` | Quiet separators and control edges |
| Primary text | `#F2F0EB` | Headings and primary content |
| Secondary text | `#A1A1AA` | Supporting interface text |
| Accent | `#C7FF2F` | Important actions and active states, used sparingly |

Use restrained, accessible success, warning, and error colors. Avoid purple gradients, excess glass effects, excessive pill controls, emoji icons, oversized empty headings, decorative noise, and heavy shadows.

### Typography

- Space Grotesk for prominent headings.
- Inter for general interface text.
- JetBrains Mono for technical metadata, timestamps, and selected numerical values.
- Keep the type scale and line spacing consistent. Do not load fonts from a remote service at runtime; use local font files when available and a sensible system fallback otherwise.

### Visual language

Use a dark, elegant, clean layout with balanced negative space, subtle borders, modest surface elevation, Lucide icons, accessible focus styles, and high-quality creative previews. Motion should be brief, purposeful, and disabled or reduced when the user requests reduced motion.

## 3. Application shell

Use a consistent shell with a collapsible left sidebar, a top navigation row, and a workspace area that adapts to the active tool.

### Left sidebar

Provide readable navigation for:

1. Overview
2. Campaigns
3. Creative Studio
4. Video Studio
5. Brand Kit
6. Media Library
7. Exports
8. Settings

Include the CreativeForge AI logo and wordmark, a New Project action, the current workspace or brand, a visible active-page indicator, and preferences where appropriate. Do not rely on icons alone. Unfinished workspaces must be visibly marked in progress and must not present active controls that do nothing.

### Top navigation

Show the current page or project title, useful breadcrumbs, global search only when implemented, real AI provider status, real event notifications, and user preferences. Never show fake notifications or activity.

## 4. Dashboard experience

The dashboard should make the next useful action clear. Include a welcome area, prominent Create Campaign action, recent projects and campaigns, recent exports, brand selection, actual AI connection status, and useful quick actions. Use stored data only; do not invent counts, performance, customer, revenue, or engagement statistics. A new workspace needs a polished empty state and a route to each implemented area.

## 5. Campaign creation experience

Use an intuitive guided workflow with visible progress:

1. Select brand.
2. Describe product or service.
3. Identify target audience.
4. Choose marketing objective.
5. Select platforms.
6. Provide offer and campaign details.
7. Generate strategy.

Group fields logically, add short examples only when useful, preserve inputs when moving between steps, and allow users to revisit earlier steps. A saved campaign workspace should organize strategy, audience, marketing angles, headlines, scripts, captions, storyboard, and creative assets. Generated content must be editable and savable.

## 6. AI assistant experience

The assistant must use current project, selected brand, and active workspace context. It should support campaign analysis, improvement suggestions, selected-copy rewrites, creative concepts, storyboard changes, video edit proposals, error explanations, and workflow guidance. Show the provider, model, and local/cloud processing status; use useful loading and error states. Keep suggestions contextual and provide Apply, Copy, Edit, and Regenerate actions as appropriate. Never overwrite user work without clear authorization.

## 7. Graphic design workspace

Treat graphic design as a dedicated editing workspace:

- **Left panel:** media, brand assets, templates, layers, and uploads.
- **Canvas:** design surface, zoom, guides, and selection handles.
- **Inspector:** position, dimensions, typography, color, opacity, alignment, and layer controls.
- **Toolbar:** project name, undo, redo, save state, resize, and export.

Support selecting, moving, resizing, and arranging elements. Use sensible typography, spacing, and alignment defaults. Provide aspect-ratio previews. The result must be a real composition that can be exported, not a static mockup.

## 8. Video editing workspace

Design a desktop-first editing environment:

- **Top toolbar:** project title, undo/redo, save state, preview quality, export.
- **Media panel:** imported clips, audio, images, graphics, and text assets.
- **Preview:** large video preview, playback controls, position, resolution, and preview settings.
- **Inspector:** selected clip transform, scale, position, opacity, volume, duration, and effects.
- **Timeline:** tracks, ruler, playhead, video/image/text/audio/subtitle tracks, visibility/lock controls, and zoom.

Make selected clips and track relationships clear. Timeline elements must correspond to real project data. Use lightweight previews; render final quality separately. Restore project state when returning to the editor. On small screens provide review and simple adjustment rather than squeezing the full desktop timeline into a phone layout. Add practical, discoverable keyboard shortcuts where supported.

## 9. Export experience

Show the actual image/video preview, platform preset, aspect ratio, resolution, frame rate, quality, audio settings, destination, and measurable output details. Display real rendering progress. After a verified success show filename, format, size, location, preview/playback, and export-again actions. On failure explain the error and preserve the source project.

## 10. Interaction and UX rules

Every interactive element must perform a meaningful action. Use consistent controls, validation, save indicators, loading indicators, useful event toasts, confirmation for destructive actions, undo/redo for meaningful edits, empty/error/success states, tooltips, keyboard access, and predictable navigation. Use direct status language such as “Saving…”, “All changes saved.”, “Exporting…”, “Export completed.”, “AI provider unavailable.”, and “No media imported yet.” Protect work against accidental loss.

## 11. Motion

Use subtle transitions for sidebar collapse, navigation, dialogs, dropdowns, panel changes, hover, and progress. Avoid constant animation, unnecessary loading motion, long transitions, or delayed actions. Respect reduced-motion preferences and prioritize performance.

## 12. Responsiveness and accessibility

Design primarily for desktop, while supporting laptop, small desktop, tablet, and mobile dashboard/campaign/brand/review work. Prevent ordinary pages from overflowing horizontally. Editing surfaces may scroll appropriately. Ensure contrast, semantic controls, labels, visible keyboard focus, and status cues that do not rely on color alone.

## 13. Reusable design system

Create shared buttons, icon buttons, inputs, textareas, selectors, dropdowns, tabs, dialogs, tooltips, toasts, panels, sidebars, navigation, empty/loading states, status indicators, file cards, media previews, project rows, and export progress components. Define CSS variables for colors, type, spacing, and radii. Avoid scattering hardcoded design values across screens.

## 14. Design quality assurance

Inspect at 1440px, 1280px, 1024px, and 390px. Check navigation, spacing, clipping, overflow, readability, active states, dialogs, dropdowns, keyboard navigation, loading/empty states, and editing-surface usability. Capture screenshots when possible and inspect them. Verify real interactions rather than judging appearance alone.

## 15. Implementation order

1. Define design tokens.
2. Establish the application shell.
3. Establish reusable UI components.
4. Design the dashboard.
5. Design the campaign workflow.
6. Implement each specialist workspace around its real function.

Build UI and backend functionality together where feasible. Keep design quality present throughout implementation. Do not use static mockups as substitutes for working screens or mark a feature complete because its interface exists.

**Design principle: every screen must look professional, make sense to use, and perform the function it promises.**
