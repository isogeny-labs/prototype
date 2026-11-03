# Gaps

Things the spec asked for that this checkpoint does not fully deliver, with the reason and the plan.

| Gap | Status | Note |
|---|---|---|
| `public/brand/isogeny-logo.svg` | **Missing** | No SVG master was supplied; the two logo images provided earlier are raster crops. The shell tries the SVG path first, then `public/brand/isogeny-logo-dark.png` (the supplied crop), then a text wordmark "Isogeny Labs". Drop an SVG at the expected path and it is used automatically. |
| Light theme | Not built | Dark mode only, by spec. Tokens are in `src/theme/tokens.ts` so a light theme is one more value per token. |
| Engineering and legal sample projects | Phase 2 | Pack templates exist as data; packs show *Coming in Phase 2*. |
| Assistant conversation UI | Phase 3 | The panel slot and the mock `AssistantService` (view-config only, refusals routed to approvals, audit events) exist; the chat controls do not yet. |
| Approval decision controls | Phase 3 | Records render; the mock `ApprovalService.decide` already blocks self-approval and already-decided requests. |
| Developer state switcher (loading / empty / error / long / permission-denied per page) | Phase 3 | Latency and failure injection exist at `/settings/sample-data`; the per-page switcher is not built. |
| Report preview, handoff and compliance export | Phase 3 | Reports page shows the structure; export buttons return mock metadata only. |
| `docs/FRONTEND_SPEC.md`, `docs/BACKEND_HOOKUP_CHECKLIST.md`, acceptance-test suite (spec section 10) | Phase 4 | |
| Criteria editing form, external-change form, artifact import form | Later phase | Mock methods (`proposeCriteriaVersion`, `reportExternalChange`, `importArtifactVersion`) exist and are unit-reachable. |
| Icons | Inline glyphs only | No icon library (none in the stack). Status is always shape + text, never colour alone. |
