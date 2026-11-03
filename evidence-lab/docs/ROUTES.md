# Routes

All routes render inside the app shell (left nav, project switcher, pack badge, sample-data banner, assistant slot).
Project routes are guarded: the project and its template version load first; loading and failed states are shown.

| Route | Page | What it shows (Phase 1, cryptography sample) |
|---|---|---|
| `/` | Home | Project cards (pack badge, status, unresolved findings, pending approvals, run count) and the three packs with availability. |
| `/p/:id` | Overview | Template-driven workspace: key metrics against the current acceptance criteria (each value links to its run and states its definition), attack-assessment table (crypto pack panel, filter by attack model), next actions, what is not tested, recent activity, disclaimers. Honors view configuration (hidden panels, order). |
| `/p/:id/intake` | Intake | Goal, constraints, intake questions (open / answered / assumed), budget, execution mode, acceptance-criteria versions with approval state. |
| `/p/:id/artifacts` | Artifacts | Artifacts with version chains: hash, size, provenance, importer, notes, planted-defect marker. |
| `/p/:id/tests` | Tests | Test definitions: kind, acceptance rule, runner and limits, run count. Runnable tests get *Request run* (creates a simulated run awaiting execution approval). Unsupported/imported tests show *Not runnable here* with the path. |
| `/p/:id/research` | Research | Experiment proposals: protocol version, hypothesis, outcomes, budget, history, result runs, follow-up suggestions. |
| `/p/:id/conductor` | Conductor | Task graph by dependency step: owner (human / tool / agent), status, budget bar, checkpoint, produced run. Pause / resume / cancel (mock). |
| `/p/:id/runs` | Runs | Append-only run list: test, artifact version, execution mode, provenance, status, pass/fail, superseded marker, label. Toggle superseded runs. |
| `/p/:id/runs/:runId` | Run detail | Full record (environment, tool versions, parameters, seeds, approval), evidence record with integrity level, metrics with definitions, criteria results, cases, log, limitations, checks. Supersedes / superseded-by notes. Retry for failed runs (new record). |
| `/p/:id/findings` | Findings | Plain-language statements with computed evidence label, user-facing status, origin, evidence counts, conflict warning. |
| `/p/:id/findings/:fid` | Finding detail | Label with the reason it was computed, checks (kind, result, who), disagreements with investigation link, assumptions/limitations, technical detail (one click down), timeline, evidence links, recommendation, resolution eligibility. |
| `/p/:id/approvals` | Approvals | Pending and decided approval records (who requested, why a human decides, who decided, note) and the template's gates. Decision buttons arrive in Phase 3. |
| `/p/:id/changes` | Changes | Recommendations typed as *supported by this project* / *general guidance* / *hypothesis*; external changes reported by the customer; before/after comparison tables. |
| `/p/:id/reports` | Reports | Report structure preview: summary and disclaimers, findings with labels, criteria coverage, evidence records. Export buttons call the mock (no file). Full preview in Phase 3. |
| `/p/:id/settings` | Project settings | Members and roles, confidentiality, execution mode, template details, budget. Read-only. |
| `/p/:id/memory` | Memory | Customer-scoped organisational memory, agent configuration changes (evaluation status), model-training record (*not in MVP*). |
| `/settings/sample-data` | Sample data | Fixture counts, reset, acting-user switch, mock latency / failure injection. |
| `*` | Not found | Empty state with a link home. |

The nav list lives in `src/shell/nav.ts`; the router in `src/router.tsx`.
