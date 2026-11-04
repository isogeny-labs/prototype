# Frontend spec (short)

## Purpose

Isogeny Labs Evidence Lab is an active lab for human-supervised research and testing. One shared workflow,
shown through three bounded domain packs (Cryptography, Mechanical Engineering, Legal):

choose a pack → intake and import existing work → configure a workspace from a pack template → import, select or
propose tests → approve execution → run supported investigations → examine evidence and inconsistencies → human
decision → improve and retest.

This frontend makes the whole workflow clickable on realistic sample data with no backend. Every service call goes
through interfaces in `src/services/types.ts`; the mocks are replaced by one switch in `src/services/index.ts`.

Never shown: a universal security score, a "secure" badge, a certification stamp, or a win probability.

## Shell

Left navigation (every route reachable directly), project switcher, pack badge (pack · template version),
persistent sample-data banner, assistant panel, and, in sample mode, a developer view-state switcher.

## Pages

| Route | Page |
|---|---|
| `/` | Home: projects and packs |
| `/p/:id` | Workspace rendered from the pack template (shared panels + pack panels) |
| `/p/:id/intake` | Goal, constraints, intake questions, budget, execution mode, versioned acceptance criteria (propose a version) |
| `/p/:id/artifacts` | Versioned artifacts with hashes and provenance |
| `/p/:id/tests` | Imported / supported / proposed tests; unsupported tests never runnable; request a run |
| `/p/:id/research` | Autoresearcher proposals with full protocol fields and the review flow |
| `/p/:id/conductor` | Task graph: owners, dependencies, budgets, checkpoints; pause / resume / cancel |
| `/p/:id/runs`, `/runs/:runId` | Append-only runs; full record, evidence record, metrics with definitions, cases, log, retry |
| `/p/:id/findings`, `/findings/:fid` | Claims with checks, conflicts, computed label, timeline, resolution eligibility |
| `/p/:id/approvals` | Decisions as records; approve / reject / request changes; roles and separation of duties |
| `/p/:id/changes` | Recommendations by claim type; report external change; request retest; before/after comparisons |
| `/p/:id/reports` | Engineering handoff and evidence-bundle previews; export simulated |
| `/p/:id/settings` | Execution modes (both shown, integration pending), integrations, permissions, template, budget |
| `/p/:id/memory` | Organisational memory, agent configuration changes, model training (not in MVP), kept separate |
| `/settings/sample-data` | Reset, acting user, mock latency and failure injection |

Details in `docs/ROUTES.md`.

## Components

`EvidenceLabel`, `CheckBadge`, `IntegrityBadge`, `ExecutionModeBadge` (+ `ProvenanceBadge`), `RunStatus`,
`FindingTimeline`, `ApprovalCard`, `ComparisonTable`, `ProposalCard`, `TaskGraph`, `ArtifactVersionList`,
`SampleBanner`, `EmptyState`, `ErrorState`, `LoadingState`, plus `Marker`, `PackBadge`, `PageHeader`,
`QueryBoundary`, `MemberSwitcher`. Pack panels live in `src/packs/<pack>/` and are registered by name.

## Evidence visual rules

- Five check kinds, one language, shape + text never colour alone: agent claim ◌, deterministic ⚙, model judgment ◐,
  human decision ✓, reproduced ⟲. Each check names its model and version or its reviewer.
- Evidence label is computed from checks (`computeEvidenceLabel`): Expert-reviewed > Machine-checked > Model-reviewed >
  Imported > Estimate. Agreement between agents never raises it.
- Integrity badges: imported, hashed, signed, Cairn-verified. Nothing in sample data is signed or Cairn-verified;
  the Cairn mock never upgrades a record.
- Execution-mode badges: platform sandbox, customer-side, imported, simulated. Provenance: measured, imported, illustrative.
- Every sample or simulated value carries a visible marker; the banner is persistent.
- Plain conclusion first; technical detail one click below.
- Disagreements stay visible with an "investigate" action that drafts a proposal. No majority voting.
- Pack disclaimers appear wherever results appear: engineering results are not physical certification; legal
  rehearsal is a preparation exercise, not a prediction; passing the available tests does not prove a
  cryptographic implementation secure.

## Assistant

Rule-based and simulated (no model connected), behind `AssistantService`. It reads the project records and can
summarise the evidence, say where it is thinnest, propose experiments and runs, review orchestration, executions,
proposals and what is waiting on the user, and change how views are laid out.

Hard rules (kept by the mock and required of any connected implementation):

1. `send` never mutates project data. View configuration changes are the only side effect, and they are audited.
2. Anything that would change the project appears as a **suggested action card**. It executes only through
   `confirm`, which the UI calls on an explicit human click, and it runs **as that human** (requester / reviewer).
3. Approval gates still apply afterwards: execution approval, protocol approval, owner approval, resolution.
4. Acceptance criteria, permissions and test definitions are never changed directly: the assistant drafts a
   criteria version, a settings-change request, or an experiment proposal.
5. The assistant never starts a run, approves anything, or applies a recommendation on its own.

## Sample stories

- **Cryptography: Acme Pay signing service.** acme-sign 1.4.2 accepts the all-zero signature (same class as
  CVE-2022-21449; the library is fictional). Malformed-input test fails; the Autoresearcher proposes an r/s range
  fuzz; a reviewer approves protocol v1; the simulated run confirms it (63 of 2000 sampled pairs, all r = 0);
  recommendation "reject r or s outside [1, n−1]" is approved; 1.4.3 is imported and retested; comparisons show the
  failing case passes with no latency regression. A second finding (latency, two disagreeing agents) stays Estimate.
- **Engineering: Mounting bracket MB-200.** 6061-T6 (276 MPa), 2.0 kN tip load, SF ≥ 2.0. v1: 162 MPa (SF 1.70)
  on an automatic mesh; convergence study 139/150/171 MPa, 14% between the last two levels, not converged; refined
  171 MPa (SF 1.61). Fillet study approved; 5 mm fillet; v2 118 MPa (SF 2.34), converged at 1.7%; imported strain gauge
  within 5% at the gauge location.
- **Legal: Northwind Supply v. Harbor Fabrication (fictional).** Fact check: brief says 3 March, receipt says
  10 March (page 1, line 8). Quotation check: a fictional authority is misquoted; the diff is shown. Contrary-authority
  search (model judgment) surfaces a fictional waiver case. The responsible lawyer approves the revised argument; brief
  v2 passes. Rehearsal panel labelled "Preparation exercise, not a prediction of the outcome". Matter marked confidential;
  document-handling controls integration pending.
