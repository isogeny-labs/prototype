# Isogeny Labs Evidence Lab — frontend skeleton

Navigable React frontend for the Evidence Lab, populated with realistic **sample data** and **no backend**.
Every service call goes through a mock layer behind contracts in `src/contracts/`; a real client replaces
the mocks by changing one switch in `src/services/index.ts`.

Everything shown is fictional and marked as such: a persistent sample-data banner, `Sample` / `Simulated`
markers on every illustrative value, and pack disclaimers wherever results appear. No login exists in this
skeleton; "acting as" is a developer switch at `/settings/sample-data`.

## Stack (pinned exact versions, see `package.json`)

React 18 · TypeScript (strict) · Vite · React Router · Tailwind CSS · Zustand · Vitest + React Testing Library · Playwright.
Supporting tooling: PostCSS/Autoprefixer (Tailwind's pipeline), jsdom (Vitest DOM), `@types/react*`, `@vitejs/plugin-react`.

## Install, run, test, reset

```bash
cd evidence-lab
npm ci                 # exact versions from package-lock.json
npm run dev            # http://127.0.0.1:5173
npm run build          # typecheck + production build into dist/
npm run preview        # serve dist/ on http://127.0.0.1:4173
npm test               # unit tests (Vitest)
npm run test:e2e       # Playwright (builds nothing: run `npm run build` first; starts `npm run preview` itself)
npm run reset-sample-data
```

Playwright needs a Chromium. `npx playwright install chromium` downloads one; if a Chromium already exists,
point at it with `PW_CHROMIUM_PATH=/path/to/chromium npm run test:e2e`.

**Reset sample data:** the app holds sample data in memory and reloads it from `src/fixtures/` on every page load.
Changes made in the UI (requested runs, decisions, reported changes) live until reload or until you press
*Reset to sample data* at `/settings/sample-data`. The `reset-sample-data` script prints this reminder.

## Layout

```
src/contracts/     domain types + the two pure rules (evidence label, finding status mapping)
src/services/      service interfaces (types.ts), mock implementations (mock/), the switch (index.ts)
src/fixtures/      JSON sample data: packs/ (templates) and one folder per sample project (crypto, engineering, legal)
src/packs/         pack-specific workspace panels, registered by name in registry.tsx
src/store/         Zustand store: in-memory db, mock config (latency, failure injection), acting user, view config
src/theme/         tokens.ts (the only place colours live) + index.css
src/components/    EvidenceLabel, CheckBadge, IntegrityBadge, ExecutionModeBadge, RunStatus, FindingTimeline,
                   ApprovalCard, ComparisonTable, ProposalCard, TaskGraph, ArtifactVersionList, SampleBanner,
                   EmptyState, ErrorState, LoadingState, …
src/shell/         AppShell (nav, project switcher, pack badge, banner, assistant slot), routing guards
src/pages/         one file per route
tests/unit/        fixture consistency + label/status rules
tests/e2e/         every route renders with sample data; no console errors; nothing scrolls horizontally at 1024px
docs/              ROUTES, ASSUMPTIONS, GAPS, INTEGRATION_CONTRACTS (mapping notes); FRONTEND_SPEC and
                   BACKEND_HOOKUP_CHECKLIST arrive with Phase 4
public/brand/      logo assets (see docs/GAPS.md about the missing SVG master)
```

## Mock layer controls

`/settings/sample-data` exposes the mock's per-call latency, a random failure rate, a one-shot "fail the next
call to …" switch, and the acting user. Latency and failure rate persist in `localStorage` (guarded; the app
works without storage).

## Hosted preview

Pushes to the repository's default branch build and deploy this app to GitHub Pages at
`https://isogeny-labs.github.io/prototype/` (see `.github/workflows/pages.yml`). The build uses
`npm run build:pages`, which sets the `/prototype/` base path and copies `index.html` to `404.html` so deep links
into client-side routes work. Sample data only; nothing is persisted.

## Phases

1. Scaffold, theme, shell, routing, contracts, mock layer, cryptography sample end to end — done.
2. Engineering and legal samples on the same shell and components — **this checkpoint**.
3. States, assistant conversation, approval decisions, memory page, report preview.
4. Docs and acceptance tests.
