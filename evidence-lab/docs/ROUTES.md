# Routes

All routes render inside the app shell (left nav, project switcher, pack badge, sample-data banner, assistant slot).
Project routes are guarded: the project and its template version load first; loading and failed states are shown.

| Route | Page | What it shows (all three sample projects) |
|---|---|---|
| `/` | Home | Project cards (pack badge, status, unresolved findings, pending approvals, run count) and the three packs with availability. |
| `/p/:id` | Overview | Template-driven workspace. Shared panels: key metrics against the current acceptance criteria (each value links to its run and states its definition), next actions, what is not tested, recent activity, disclaimers. Pack panels by template: crypto attack assessment; engineering model setup, schematic stress view, mesh convergence; legal chronology, disputed facts, document viewer (deep links `?doc=&page=&line=`), argument map, authorities, rehearsal. Honors view configuration (hidden panels, order). |
| `/p/:id/intake` | Intake | Goal, constraints, intake questions (open / answered / assumed), budget, execution mode, acceptance-criteria versions with approval state. Proposing a new version creates a pending version and an owner approval request. |
| `/p/:id/artifacts` | Artifacts | Artifacts with version chains: hash, size, provenance, importer, notes, planted-defect marker. |
| `/p/:id/tests` | Tests | Test definitions: kind, acceptance rule, runner and limits, run count. Runnable tests get *Request run* (creates a simulated run awaiting execution approval). Unsupported/imported tests show *Not runnable here* with the path. |
| `/p/:id/research` | Research | Experiment proposals: protocol version, hypothesis, outcomes, budget, history, result runs, follow-up suggestions; review flow (approve as a numbered protocol, reject, request changes) for proposals with a pending approval. |
| `/p/:id/conductor` | Conductor | Task graph by dependency step: owner (human / tool / agent), status, budget bar, checkpoint, produced run. Pause / resume / cancel (mock). |
| `/p/:id/runs` | Runs | Append-only run list: test, artifact version, execution mode, provenance, status, pass/fail, superseded marker, label. Toggle superseded runs. |
| `/p/:id/runs/:runId` | Run detail | Full record (environment, tool versions, parameters, seeds, approval), evidence record with integrity level, metrics with definitions, criteria results, cases, log, limitations, checks. Supersedes / superseded-by notes. Retry for failed runs (new record). |
| `/p/:id/findings` | Findings | Plain-language statements with computed evidence label, user-facing status, origin, evidence counts, conflict warning. |
| `/p/:id/findings/:fid` | Finding detail | Label with the reason it was computed, checks (kind, result, who), disagreements with investigation link, assumptions/limitations, technical detail (one click down), timeline, evidence links, recommendation, resolution eligibility. |
| `/p/:id/approvals` | Approvals | Pending and decided approval records (who requested, why a human decides, who decided, note) and the template's gates. Approve / reject / request changes with a note; the acting user can be switched among project members (sample mode). Self-approval and wrong-role decisions are refused with a visible reason. |
| `/p/:id/changes` | Changes | Report an external change (finding, new artifact version, description); recommendations typed as *supported by this project* / *general guidance* / *hypothesis*; reported changes with a one-click retest request (goes to execution approval); before/after comparison tables. |
| `/p/:id/reports` | Reports | Engineering handoff preview (scope, what was tested, criteria results, findings with labels and limits, recommendations and retests, what is not established, decisions) and evidence-bundle preview (manifest, members, hashes, unsigned, how to verify). Export is simulated. |
| `/p/:id/settings` | Project settings | Members and roles, confidentiality, execution mode, template details, budget. Read-only. |
| `/p/:id/memory` | Memory | Customer-scoped organisational memory, agent configuration changes (evaluation status), model-training record (*not in MVP*). |
| `/settings/sample-data` | Sample data | Fixture counts, reset, acting-user switch, mock latency / failure injection. |
| `*` | Not found | Empty state with a link home. |

The nav list lives in `src/shell/nav.ts`; the router in `src/router.tsx`. The shell adds the assistant panel (advisory: summaries and confirmable suggested actions; view configuration is its only direct side effect) and, in sample mode, the developer view-state switcher.
