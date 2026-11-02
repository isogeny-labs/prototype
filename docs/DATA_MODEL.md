# Data model
```
Project ─┬─ ProjectMember (owner|editor|reviewer|viewer)
         ├─ InventoryItem (provenance: user_reported | detected | independently_tested)
         ├─ Requirement (metric, operator, threshold, applies_to all|measured|imported)
         ├─ Implementation (manifest, purpose, algorithm, library, dependencies, source_revision, source_snapshot_artifact_id,
         │                  source_digest, adapter_kind profile|module|results_only, compatibility, parent_id, recommendation_id,
         │                  change_report, seeded_defect, status imported|baseline|candidate|superseded|retired)
         ├─ TestDefinition (test_id, version, fixture, definition, acceptance_criteria, resource_limits)
         ├─ Run  APPEND-ONLY (execution_mode, provenance, classification, runner/fixture versions, environment, commands, inputs,
         │        resource_limits, metrics, metric_definitions, scenarios, raw_output_artifact_id, failures, exclusions, limitations,
         │        artifact_hashes, requirement_results, evidence_labels[], bundle_id, external_run_id, runner_reported_executed_at,
         │        received_at, duplicate_of_run_id, stale_reason, supersedes_run_id, correction_note, experiment_proposal_id, protocol_version)
         ├─ Artifact (sha256, storage_path, kind raw_output|source_snapshot|import|bundle)
         ├─ EvidenceBundle (kind platform|customer_runner, envelope (original), statement, signer, verification, countersignature)
         ├─ TrustedKey (project or platform-wide, key_id, public_key_pem, purpose, status active|revoked)
         ├─ Finding (kind implementation_defect|requirement_failure|research_claim|manual, reproduction_status, failing_scenarios,
         │           status open → recommendation_proposed → external_change_reported → awaiting_retest →
         │           resolved_within_tested_scope | still_failing | inconclusive, revised_implementation_id, evidence_run_ids)
         ├─ Recommendation (category, guidance_kind best_practice|hypothesis|project_specific, body{observed_issue, supporting_evidence,
         │                  proposed_change, authoritative_guidance, expected_benefit, tradeoffs, applicability_limits, required_retest})
         ├─ Approval (subject_type, subject_id, decision, reviewer)
         ├─ ResearchSource (untrusted content, sha256)
         ├─ ExperimentProposal (research_question … cannot_establish, allowlisted_fixture, status proposed|approved|rejected|executed|reviewed)
         │     └─ ProtocolVersion (frozen protocol JSON, sha256, approved_by, supersedes_version)
         └─ AttackAssessment (category reproduced_weakness|measured_experiment|estimated_effort|published_estimate|unknown, attack_model)
AuditEvent · User · SessionToken · Job
```
