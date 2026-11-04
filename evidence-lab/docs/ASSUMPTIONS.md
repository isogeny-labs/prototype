# Assumptions

## Ground truth about the backend (from the spec)

Recorded here as given; the frontend treats none of these as connected or validated.

- The runner executes only allowlisted Python fixtures.
- A Docker runner is unvalidated.
- No customer code runs yet.
- Evidence export is a SHA-256 manifest with a verify step; it is not signed.
- The coordination service ("Conductor", Go) and the evidence service ("Cairn", Rust, with re-runnable checkers
  and signed checkpoints) exist in separate repositories and are not connected to the prototype.
- The Autoresearcher has only run on cryptography.
- There is no engineering solver integration and no legal document or citation code.
- Record names and fields in the prototype: Project, ProjectMember, Requirement, Implementation, Experiment, Run,
  Artifact, Recommendation, Approval, ResearchSource, Finding, AttackAssessment, SandboxExperiment, Job, AuditEvent.
  The mapping in `docs/INTEGRATION_CONTRACTS.md` assumes these names and the stated finding lifecycle.

## Discrepancy with the current prototype backend in this repository

The spec's facts describe the earlier MVP. The backend that currently lives in `../backend` and `../iel_tools`
went further in a later revision: DSSE / in-toto signed evidence bundles, a standalone verifier, a sandboxed
customer-side runner with adapters, and a finding lifecycle that differs in naming. Both are recorded here;
the frontend follows the spec (unsigned manifests, no Cairn, runner limits) and the contracts carry the
fields needed for either (for example `EvidenceRecord.integrity` has `signed`). When the backend owner
connects a real client, `docs/INTEGRATION_CONTRACTS.md` lists the fields to map.

## Decisions taken in this checkpoint

1. **Location.** The frontend lives in `evidence-lab/` inside this repository, next to the MVP. The MVP,
   its CI and the GitHub Pages demo are untouched. Nothing was written to any other repository.
2. **Logo.** No SVG master exists; raster crops supplied earlier are used with a wordmark fallback (see GAPS).
3. **Tooling dependencies.** PostCSS, Autoprefixer, jsdom, `@types/react`, `@types/react-dom`,
   `@vitejs/plugin-react`, `@testing-library/jest-dom` and `@testing-library/user-event` are treated as part
   of the named stack (Tailwind, Vitest/RTL and Vite require them). No icon, chart, date or state library was
   added. `@types/node` was deliberately not added; `vite.config.ts` avoids Node globals.
4. **Fixture dates and people.** All dates are October 2026; all people, organisations ("Acme Pay"),
   libraries ("acme-sign") and the Wycheproof *subset numbering* are fictional. The planted defect class
   (missing range check on r and s) is real and well known; the library carrying it is invented.
5. **Sample runs** carry `provenance: "illustrative"` so every number renders with a *Sample value* marker.
   Execution mode `simulated` marks runs that no runner produced even in the story (the Autoresearcher's
   protocol runs); `platform_sandbox` runs are the story's baseline runs.
6. **Evidence label for runs.** The spec defines the label for findings. For run rows, a run with checks
   referencing it uses the same rule; otherwise a completed deterministic run is *Machine-checked*, imported
   results are *Imported*, a simulated run is *Estimate*, an unfinished run has no label.
7. **Pack data.** Core records are domain-neutral; crypto-only fields (attack assessments, build identity,
   source revision, configuration, vector source) sit in `packData` discriminated by `packId`. The backend's
   AttackAssessment categories A–D map to four of the five panel kinds; "No defensible estimate available" is the
   explicit absence of a category.
8. **Finding status.** `retested` with a passing latest retest displays as *Resolved within tested scope*
   even before the `finding_resolution` approval moves the backend status to `closed`; the detail page says
   which backend status is behind the shown state. Home counts findings as unresolved by the user-facing status.
9. **Compute unit** is defined in the UI as "one sandbox slot for one hour on the reference profile (sample
   definition)" because the spec names the unit but not its meaning.
10. **Integrity.** No sample evidence record is `signed` or `cairn_verified`, and the mock `CairnService`
   never upgrades a record.
11. **No universal score.** Nothing renders a security score, a "secure" badge, a certification stamp or a win
    probability. Attack assessments are a table of typed statements with explicit uncertainty.
12. **Engineering numbers.** Run #1 (automatic mesh) gives 162 MPa; the convergence study uses three *structured*
    refinement levels at the fillet (139 / 150 / 171 MPa) that do not include the automatic mesh, so 162 is not
    one of the levels. 14% is the change between the last two levels; 171 MPa (SF 1.61) is the refined result that
    supersedes run #1 for criteria purposes. v2: 118 MPa (SF 2.34), converged at 1.7%. The strain gauge checks a
    point 30 mm from the fillet (61.8 vs 58.9 MPa), not the peak.
13. **Legal documents.** All documents, parties, people, dates and authorities are fictional. Document checks are
    `simulated` because no legal document or citation code exists. The brief is the artifact under test; v2 is a
    customer-made revision reported as an external change.
14. **Execution mode of engineering and legal runs** is `simulated` with `illustrative` provenance, because no solver
    or document checker is connected; the crypto baseline runs use `platform_sandbox` because an allowlisted
    crypto fixture runner exists in the prototype backend.
15. **GitHub Pages.** The Pages workflow now deploys this frontend at `/prototype/` with a `404.html` fallback for
    client-side routes. The earlier MVP static demo is no longer published by the workflow; the single-file copy
    `demo/iel-demo.html` remains in the repository.
16. **Assistant scope (changed at the Phase 3 review).** The original brief limited the assistant to view
    configuration. The product owner widened it: the assistant may brainstorm about everything on the platform,
    summarise evidence, review orchestration, executions and proposals, and suggest next steps. The reconciliation
    kept in code and docs: the assistant proposes, the human confirms; a confirmed action runs as that human; approval
    gates still apply; criteria, permissions and test definitions are never changed directly (drafts only); the
    assistant never starts a run or approves anything on its own.
