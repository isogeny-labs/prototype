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
| Assistant conversation UI | Phase 3 | The panel slot and the mock `AssistantService` (view-config only, refusals routed to approvals, audit events) exist; the chat controls do not yet. |
| Approval decision controls | Phase 3 | Records render; the mock `ApprovalService.decide` already blocks self-approval and already-decided requests. |
| Developer state switcher (loading / empty / error / awaiting-approval / completed per view) | Phase 3 | Latency and failure injection exist at `/settings/sample-data`; the per-view switcher is not built. |
| Report preview, handoff and compliance export | Phase 3 | Reports page shows the structure; export buttons return mock metadata only. |
| `docs/FRONTEND_SPEC.md`, `docs/BACKEND_HOOKUP_CHECKLIST.md`, full acceptance-test suite (spec section 10) | Phase 4 | Route, consistency, label, comparison and disclaimer tests already run; approvals, failure injection, assistant refusal and reset tests arrive with Phase 3 features. |
| Criteria editing form, external-change form, artifact import form | Later phase | Mock methods exist and are unit-reachable. |
| Engineering viewer | Placeholder | A schematic SVG coloured by region from the run's stress table; no CAD or mesh rendering. |
| Legal document handling | Integration pending | Privilege tagging, redaction and access logging are not built; the sample marks the matter confidential and the email thread "not privileged" by explicit assumption. |
| Second crypto project "Public campaign: ECC2K-130" | Not started | Optional stretch per spec, after the three core samples pass. |
| Icons | Inline glyphs only | No icon library (none in the stack). Status is always shape + text, never colour alone. |
