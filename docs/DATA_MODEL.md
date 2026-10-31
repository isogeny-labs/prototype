# Data model (shared by the IoT and application workflows)

```
Project ─┬─ ProjectMember (role)            Job (queue: run_fixture | research_review | sandbox_execute)
         ├─ InventoryItem (provenance: user_reported | imported | verified)
         ├─ Requirement (metric, operator, threshold, applies_to: all | measured | imported)
         ├─ Implementation (role baseline|candidate, status, profile_id, source_revision, configuration,
         │                  target_environment, build_identity, delivery_mode, parent_id, recommendation_id)
         │     └─ Task
         ├─ Experiment (fixture, definition, acceptance_criteria)
         ├─ Run  (APPEND-ONLY: provenance measured|imported|illustrative, runner/fixture versions, environment,
         │        commands, repeat_count, metrics, metric_definitions, scenarios, raw_output_artifact_id,
         │        failures, exclusions, limitations, artifact_hashes, requirement_results, overall_pass,
         │        supersedes_run_id, correction_note)
         ├─ Artifact (sha256, storage_path)
         ├─ Recommendation (kind migration|configuration|no_migration|remediation, status, body{…}, finding_id,
         │                  target_implementation_id, resulting_implementation_id)
         ├─ Approval (subject_type, subject_id, decision, reviewer_id, note)  — never a boolean flipped in place
         ├─ ResearchSource (content = untrusted data, content_sha256, is_demo, extraction_method)
         ├─ Finding (origin research|measurement|manual, claims[{reproduced}], affected{}, matched_inventory_ids,
         │           affected_implementation_ids, status + status_history, recommendation_id, evidence_run_ids)
         ├─ AttackAssessment (category A|B|C|D, attack_model classical|quantum, …)
         └─ SandboxExperiment (status proposed|approved|rejected|executed|verified, allowlisted_fixture, bounds)
AuditEvent (actor, action, subject, scrubbed detail)      User / SessionToken (hashed)
```

Finding statuses: `new → triage → relevant → experiment_proposed → reviewed → action_approved → retested → closed`
(plus `not_relevant`; `closed → relevant` reopens). `action_approved` requires an approved recommendation;
`retested` requires a linked passing run; `closed` requires the latest retest to pass.
