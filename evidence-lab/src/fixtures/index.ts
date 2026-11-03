/**
 * Sample data. Every project here is fictional and marked isSample.
 * JSON fixtures are cast to the contract types at the boundary; tests/unit/fixtures.test.ts checks
 * that every cross-reference (run -> artifact version, finding -> check, approval -> subject, ...) resolves.
 */
import type { Db } from "@/store/db";
import type {
  AcceptanceCriteria, AgentConfigChange, Approval, Artifact, AuditEvent, Check, Comparison, EvidenceRecord, ExperimentProposal,
  ExternalChange, Finding, MemoryItem, ModelTrainingRecord, PackInfo, PackTemplate, Project, Recommendation, Run, Task, TestDefinition, AttackAssessment,
} from "@/contracts";

import packs from "./packs/packs.json";
import templates from "./packs/templates.json";
import cryptoProject from "./crypto/project.json";
import cryptoArtifacts from "./crypto/artifacts.json";
import cryptoTests from "./crypto/tests.json";
import cryptoRuns from "./crypto/runs.json";
import cryptoChecks from "./crypto/checks.json";
import cryptoFindings from "./crypto/findings.json";
import cryptoApprovals from "./crypto/approvals.json";
import cryptoProposals from "./crypto/proposals.json";
import cryptoTasks from "./crypto/tasks.json";
import cryptoEvidence from "./crypto/evidence.json";
import cryptoChanges from "./crypto/changes.json";
import cryptoLearning from "./crypto/learning.json";
import cryptoAudit from "./crypto/audit.json";
import cryptoAttacks from "./crypto/attackAssessments.json";
import engProject from "./engineering/project.json";
import engArtifacts from "./engineering/artifacts.json";
import engTests from "./engineering/tests.json";
import engRuns from "./engineering/runs.json";
import engRecords from "./engineering/records.json";
import legalProject from "./legal/project.json";
import legalArtifacts from "./legal/artifacts.json";
import legalTests from "./legal/tests.json";
import legalRuns from "./legal/runs.json";
import legalRecords from "./legal/records.json";

const cast = <T,>(v: unknown) => v as T;

export function loadFixtures(db: Db): Db {
  db.packs.push(...cast<PackInfo[]>(packs));
  db.templates.push(...cast<PackTemplate[]>(templates));

  // Cryptography sample: "Acme Pay signing service"
  db.projects.push(...cast<Project[]>(cryptoProject.projects));
  db.criteria.push(...cast<AcceptanceCriteria[]>(cryptoProject.criteria));
  db.artifacts.push(...cast<Artifact[]>(cryptoArtifacts));
  db.tests.push(...cast<TestDefinition[]>(cryptoTests));
  db.runs.push(...cast<Run[]>(cryptoRuns));
  db.checks.push(...cast<Check[]>(cryptoChecks));
  db.findings.push(...cast<Finding[]>(cryptoFindings));
  db.approvals.push(...cast<Approval[]>(cryptoApprovals));
  db.proposals.push(...cast<ExperimentProposal[]>(cryptoProposals));
  db.tasks.push(...cast<Task[]>(cryptoTasks));
  db.evidence.push(...cast<EvidenceRecord[]>(cryptoEvidence));
  db.recommendations.push(...cast<Recommendation[]>(cryptoChanges.recommendations));
  db.externalChanges.push(...cast<ExternalChange[]>(cryptoChanges.externalChanges));
  db.comparisons.push(...cast<Comparison[]>(cryptoChanges.comparisons));
  db.memory.push(...cast<MemoryItem[]>(cryptoLearning.memory));
  db.agentConfigChanges.push(...cast<AgentConfigChange[]>(cryptoLearning.agentConfigChanges));
  db.modelTraining.push(...cast<ModelTrainingRecord[]>(cryptoLearning.modelTraining));
  db.audit.push(...cast<AuditEvent[]>(cryptoAudit));
  db.attackAssessments.push(...cast<AttackAssessment[]>(cryptoAttacks));

  // Mechanical engineering sample: "Mounting bracket MB-200"; Legal sample: "Northwind Supply v. Harbor Fabrication (fictional)"
  for (const pack of [
    { project: engProject, artifacts: engArtifacts, tests: engTests, runs: engRuns, records: engRecords },
    { project: legalProject, artifacts: legalArtifacts, tests: legalTests, runs: legalRuns, records: legalRecords },
  ]) {
    db.projects.push(...cast<Project[]>(pack.project.projects));
    db.criteria.push(...cast<AcceptanceCriteria[]>(pack.project.criteria));
    db.artifacts.push(...cast<Artifact[]>(pack.artifacts));
    db.tests.push(...cast<TestDefinition[]>(pack.tests));
    db.runs.push(...cast<Run[]>(pack.runs));
    const r = pack.records;
    db.checks.push(...cast<Check[]>(r.checks));
    db.findings.push(...cast<Finding[]>(r.findings));
    db.approvals.push(...cast<Approval[]>(r.approvals));
    db.proposals.push(...cast<ExperimentProposal[]>(r.proposals));
    db.tasks.push(...cast<Task[]>(r.tasks));
    db.evidence.push(...cast<EvidenceRecord[]>(r.evidence));
    db.recommendations.push(...cast<Recommendation[]>(r.recommendations));
    db.externalChanges.push(...cast<ExternalChange[]>(r.externalChanges));
    db.comparisons.push(...cast<Comparison[]>(r.comparisons));
    db.memory.push(...cast<MemoryItem[]>(r.memory));
    db.audit.push(...cast<AuditEvent[]>(r.audit));
  }

  // Newest audit first, as the mock services prepend.
  db.audit.sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0));
  return db;
}
