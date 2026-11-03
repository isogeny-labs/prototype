# Gaps

Things the spec asks for that the current checkpoint does not fully deliver, with the reason and the plan.

## Shared components versus pack-specific panels (first measure of reuse)

Everything on the workflow pages (Intake, Artifacts, Tests, Research, Conductor, Runs, Run detail, Findings,
Finding detail, Approvals, Changes, Reports, Settings, Memory) renders all three packs with the **same**
components and no pack branches. The pack-specific code is confined to workspace panels registered in
`src/packs/registry.tsx` and selected by each template's `workspaceLayout.panels`:

| Pack | Pack-specific panel | Why a shared component could not cover it |
|---|---|---|
| Cryptography | `AttackAssessmentPanel` | Typed attack statements (reproduced / measured / estimate / published / none) have no analogue in the other packs. |
| Engineering | `ModelSetupPanel` | Material card, loads, boundary conditions and solver assumptions are solver inputs, not workflow records. |
| Engineering | `StressViewPanel` | Schematic 2D stress map with a colour legend (placeholder, not geometry). |
| Engineering | `ConvergencePanel` | Per-level refinement results and the converged / not-converged judgement. |
| Legal | `ChronologyPanel` | Dated events each linked to a document page and line. |
| Legal | `DocumentViewerPanel` | Read-only page/line viewer with deep links (`?doc=&page=&line=`). |
| Legal | `DisputedFactsPanel` | Finding + assertion location + source location + quotation diff, plus check rows. |
| Legal | `ArgumentMapPanel` | Claims, facts, authorities, counterarguments and responses as a tree. |
| Legal | `AuthoritiesPanel` | Fictional-authority list with the mandatory "Sample authority, not a real case" label. |
| Legal | `RehearsalPanel` | Counterarguments and questions under the "Preparation exercise" disclaimer. |

Small pack-aware touches inside shared components (all driven by `packData`, no branches on the pack elsewhere):
`ArtifactVersionList` shows a fictional-authority label, a privileged tag and a fillet size when present; the
run detail renders `packData` fields generically through the run's metrics, cases and logs rather than a
dedicated view (a per-pack run-detail panel is a possible later refinement).

Where the shared workflow stretched: the engineering "artifact under test" is geometry and the legal one is the
brief, so `TEST_TARGET_KIND` in `src/lib/lookup.ts` names the kind per pack for the Tests page and the
"untested" panel.

## Remaining gaps

| Gap | Status | Note |
|---|---|---|
| `public/brand/isogeny-logo.svg` | **Missing** | No SVG master was supplied; the two logo images provided are raster crops. The shell tries the SVG path first, then `public/brand/isogeny-logo-dark.png`, then a text wordmark "Isogeny Labs". Drop an SVG at the expected path and it is used automatically. |
| Light theme | Not built | Dark mode only, by spec. Tokens are in `src/theme/tokens.ts`. |
| Assistant conversation | Done (Phase 3) | Chat in the side panel; view-configuration commands only; refusals shown and routed to an approval request; every change audited. The command grammar is a small regex set in the mock; a connected assistant replaces it behind `AssistantService`. |
| Approval decisions | Done (Phase 3) | Approve / reject / request changes with a note; self-approval blocked; gate roles enforced (owner decides anything, reviewer decides reviewer gates); resolution needs a passing retest. Decisions write memory records. |
| Developer state switcher | Done (Phase 3) | Nav control in sample mode; forces every key view into empty / loading / failed / awaiting approval / completed by reshaping read results in the mock layer; writes still hit live data. |
| Report preview and exports | Preview done; export simulated | Handoff and evidence-bundle previews render from live data; export returns mock metadata and produces no file (by spec). Compliance export format is not defined. |
| Criteria editing, external-change reporting, retest request | Done (Phase 3) | Propose-a-version form on Intake; report-change form and retest request on Changes. Artifact import form is not built (mock method exists). |
| `docs/FRONTEND_SPEC.md`, `docs/BACKEND_HOOKUP_CHECKLIST.md`, completed `INTEGRATION_CONTRACTS.md` | Phase 4 | Acceptance tests for section 10 already run (routes, consistency, labels, comparisons, disclaimers, approvals, failure injection, assistant refusal, reset). |
| Session persistence | Convenience only | Edits persist per browser tab in `sessionStorage` (guarded); a fixtures fingerprint discards stale sessions. Not a backend. |
| Engineering viewer | Placeholder | A schematic SVG coloured by region from the run's stress table; no CAD or mesh rendering. |
| Legal document handling | Integration pending | Privilege tagging, redaction and access logging are not built; the sample marks the matter confidential and the email thread "not privileged" by explicit assumption. |
| Second crypto project "Public campaign: ECC2K-130" | Not started | Optional stretch per spec, after the three core samples pass. |
| Icons | Inline glyphs only | No icon library (none in the stack). Status is always shape + text, never colour alone. |
