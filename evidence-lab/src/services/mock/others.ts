import type { ApprovalService, AutoresearcherService, ConductorService, PackRegistry, CairnService, AssistantService, LearningService } from "../types";
import { ServiceError } from "../types";
import { store } from "@/store";
import { simulate, nowIso, newId, notFound, audit } from "./base";
import type { Approval, ExperimentProposal, Task, ViewConfig, AssistantMessage, CompatibilityResult, MemoryItem } from "@/contracts";
import { canResolve } from "@/contracts";

const personName = (projectId: string, id: string) => store.db().projects.find((p) => p.id === projectId)?.people.find((p) => p.id === id)?.name ?? id;

/** Who may decide: the template's gate names a required role. Owners may decide anything; reviewers decide reviewer-gated subjects. */
function assertMayDecide(projectId: string, a: Approval, reviewerId: string) {
  const db = store.db();
  const project = db.projects.find((p) => p.id === projectId) ?? notFound("project", projectId);
  const member = project.permissions.members.find((m) => m.personId === reviewerId);
  if (!member) throw new ServiceError(`${personName(projectId, reviewerId)} is not a member of this project and cannot decide.`, "forbidden");
  const template = db.templates.find((t) => t.id === project.templateId && t.version === project.templateVersion);
  const gate = template?.approvalGates.find((g) => g.subjectType === a.subjectType);
  const required = gate?.requiredRole ?? "reviewer";
  const ok = member.role === "owner" || (required === "reviewer" && member.role === "reviewer");
  if (!ok) throw new ServiceError(`Your role in this project is ${member.role}; this decision (${a.subjectType.replace(/_/g, " ")}) needs ${required === "owner" ? "the owner" : "a reviewer or the owner"}.`, "forbidden");
}

function remember(projectId: string, item: Omit<MemoryItem, "id" | "projectId" | "customerScope" | "recordedAt">) {
  const project = store.db().projects.find((p) => p.id === projectId);
  const customerScope = project?.people.find((x) => project.permissions.members.find((m) => m.personId === x.id)?.role === "owner")?.org ?? project?.name ?? projectId;
  store.mutate((db) => { db.memory.unshift({ id: newId("mem"), projectId, customerScope, recordedAt: nowIso(), ...item }); });
}

/** Apply the consequence of a decision to the subject record. Decisions are records; subjects reference them. */
function applyDecision(projectId: string, a: Approval, decision: "approved" | "rejected" | "changes_requested", reviewerName: string) {
  const pendingMemory: Array<Omit<MemoryItem, "id" | "projectId" | "customerScope" | "recordedAt">> = [];
  store.mutate((db) => {
    const runsById = Object.fromEntries(db.runs.map((r) => [r.id, r]));
    switch (a.subjectType) {
      case "acceptance_criteria": {
        const c = db.criteria.find((x) => x.id === a.subjectId);
        if (c && decision === "approved") { c.approvalId = a.id; const p = db.projects.find((x) => x.id === projectId); if (p) p.currentCriteriaVersion = Math.max(p.currentCriteriaVersion, c.version); }
        break;
      }
      case "experiment_proposal": {
        const p = db.proposals.find((x) => x.id === a.subjectId);
        if (!p) break;
        if (decision === "approved") { p.protocolVersion += 1; p.status = "approved"; p.protocolHistory.push({ version: p.protocolVersion, approvalId: a.id, note: a.note || "approved", at: nowIso() }); }
        else if (decision === "rejected") { p.status = "rejected"; pendingMemory.push({ kind: "rejected_hypothesis", text: `Rejected: ${p.hypothesis} (${a.note || "no note"})`, sourceRef: { kind: "proposal", id: p.id }, recordedBy: reviewerName }); }
        else p.status = "proposed";
        break;
      }
      case "run_execution": {
        const r = db.runs.find((x) => x.id === a.subjectId);
        if (!r) break;
        if (decision === "approved") { r.status = "queued"; r.logs.push({ t: nowIso(), level: "info", text: `Execution approved by ${reviewerName}. Queued (simulated: no runner is connected).` }); }
        else { r.status = "failed"; r.failures.push(decision === "rejected" ? `Execution rejected by ${reviewerName}: ${a.note}` : `Changes requested by ${reviewerName}: ${a.note}`); }
        break;
      }
      case "recommendation": {
        const rec = db.recommendations.find((x) => x.id === a.subjectId);
        if (!rec) break;
        rec.status = decision === "approved" ? "approved" : decision === "rejected" ? "rejected" : "draft";
        if (decision === "approved" && rec.findingId) { const f = db.findings.find((x) => x.id === rec.findingId); if (f && ["reviewed", "relevant", "experiment_proposed"].includes(f.status)) { f.status = "action_approved"; f.statusHistory.push({ status: "action_approved", at: nowIso(), by: reviewerName, note: `Recommendation ${rec.id} approved` }); } }
        if (decision === "approved") pendingMemory.push({ kind: "accepted_finding", text: `Accepted: ${rec.title} (${rec.type.replace(/_/g, " ")}).`, sourceRef: { kind: "approval", id: a.id }, recordedBy: reviewerName });
        if (decision === "changes_requested" && a.note) pendingMemory.push({ kind: "expert_correction", text: `Correction on "${rec.title}": ${a.note}`, sourceRef: { kind: "approval", id: a.id }, recordedBy: reviewerName });
        break;
      }
      case "finding_resolution": {
        const f = db.findings.find((x) => x.id === a.subjectId);
        if (!f) break;
        if (decision === "approved") {
          const ok = canResolve(f, runsById);
          if (!ok.ok) throw new ServiceError(`Cannot resolve: ${ok.reason}`, "conflict");
          f.status = "closed"; f.statusHistory.push({ status: "closed", at: nowIso(), by: reviewerName, note: a.note || "Resolved within tested scope" });
        }
        break;
      }
      case "task_checkpoint": {
        const t = db.tasks.find((x) => x.checkpoint?.approvalId === a.id);
        if (t) t.status = decision === "approved" ? "queued" : decision === "rejected" ? "cancelled" : "awaiting_checkpoint";
        break;
      }
      case "agent_config_change": {
        const c = db.agentConfigChanges.find((x) => x.id === a.subjectId);
        if (c) c.evaluationStatus = decision === "approved" ? "evaluating" : decision === "rejected" ? "rejected" : "proposed";
        break;
      }
      default: break;
    }
  });
  for (const m of pendingMemory) remember(projectId, m);
}

export const mockApprovals: ApprovalService = {
  list: (projectId) => simulate("approvals.list", () => store.db().approvals.filter((a) => a.projectId === projectId)),
  decide: (projectId, approvalId, decision, reviewerId, note) => simulate("approvals.decide", () => {
    const a = store.db().approvals.find((x) => x.id === approvalId && x.projectId === projectId) ?? notFound("approval", approvalId);
    if (a.decision !== "pending") throw new ServiceError("This request already has a decision; decisions are records and are never overwritten.", "conflict");
    if (a.requestedBy === reviewerId) throw new ServiceError("You requested this approval, so you cannot decide it. Separation of duties: a different reviewer must decide.", "forbidden");
    assertMayDecide(projectId, a, reviewerId);
    const reviewerName = personName(projectId, reviewerId);
    applyDecision(projectId, { ...a, note }, decision, reviewerName);
    store.mutate((db) => { const x = db.approvals.find((y) => y.id === approvalId); if (x) { x.decision = decision; x.reviewerId = reviewerId; x.note = note; x.decidedAt = nowIso(); } });
    audit(projectId, { type: "human", name: reviewerName }, `approval.${decision}`, { type: a.subjectType, id: a.subjectId, label: a.subjectLabel }, note);
    return store.db().approvals.find((x) => x.id === approvalId)!;
  }),
  request: (projectId, input) => simulate("approvals.request", () => {
    const a: Approval = { ...input, id: newId("apr"), requestedAt: nowIso(), decision: "pending", reviewerId: null, decidedAt: null, note: "" };
    store.mutate((db) => { db.approvals.unshift(a); });
    audit(projectId, { type: "human", name: personName(projectId, input.requestedBy) }, "approval.requested", { type: input.subjectType, id: input.subjectId, label: input.subjectLabel });
    return a;
  }),
};

export const mockAutoresearcher: AutoresearcherService = {
  list: (projectId) => simulate("autoresearcher.list", () => store.db().proposals.filter((p) => p.projectId === projectId)),
  get: (projectId, proposalId) => simulate("autoresearcher.get", () => store.db().proposals.find((p) => p.id === proposalId && p.projectId === projectId) ?? notFound("proposal", proposalId)),
  create: (projectId, input) => simulate("autoresearcher.create", () => {
    const finding = input.findingId ? store.db().findings.find((f) => f.id === input.findingId) : undefined;
    const p: ExperimentProposal = {
      id: newId("prop"), projectId, title: `Characterise: ${(finding?.statement ?? input.prompt).slice(0, 70)}`,
      researchQuestion: `What exactly causes "${(finding?.statement ?? input.prompt).slice(0, 80)}", and under which inputs does it occur?`,
      motivation: "Simulated proposal: generated from the finding text by the mock Autoresearcher. A connected Autoresearcher would ground this in the artifact and sources.",
      sourceReferences: finding ? [{ kind: "finding", id: finding.id, label: finding.statement.slice(0, 60) }] : [],
      affectedArtifactVersionId: input.affectedArtifactVersionId,
      hypothesis: "H1: the behaviour is confined to a bounded input class that a deterministic sweep can enumerate.",
      baselineAndControls: "Baseline: the same sweep against a reference implementation that must accept zero malformed cases.",
      procedure: "Enumerate the input class with a fixed seed; record accept/reject per case; compare against the reference.",
      outcomes: { success: "H1 holds: acceptance confined to the enumerated class; control clean.", failure: "H1 refuted: acceptance broader than the class, or the control misbehaves.", inconclusive: "Sweep did not complete within budget, or results differ between repeats." },
      budget: { computeUnits: 2, timeHours: 0.5, moneyUsd: 3 }, requiredArtifacts: ["raw per-case table", "seed and parameters", "evidence record"],
      safetyBoundaries: "Synthetic keys and inputs only; sandbox with networking disabled; allowlisted fixture only.",
      wouldEstablish: "Which inputs of the enumerated class this artifact version accepts.", wouldNotEstablish: "Exploitability in production, or correctness outside the enumerated class.",
      status: "proposed", protocolVersion: 0, protocolHistory: [], proposedBy: { type: "agent", name: "Autoresearcher (simulated)", model: "sample-model (no real model connected)" },
      linkedTestDefinitionId: null, resultRunIds: [], resultSummary: "", followUpSuggestions: [], findingId: input.findingId, createdAt: nowIso(),
    };
    const approval: Approval = { id: newId("apr"), projectId, subjectType: "experiment_proposal", subjectId: p.id, subjectLabel: p.title, requestedBy: "agent-autoresearcher", requestedAt: nowIso(), decision: "pending", reviewerId: null, note: "", decidedAt: null,
      rationale: "Experiments run only with an approved, versioned protocol." };
    store.mutate((db) => { db.proposals.unshift(p); db.approvals.unshift(approval); if (finding) { const f = db.findings.find((x) => x.id === finding.id); if (f && f.status === "triage") { f.status = "experiment_proposed"; f.statusHistory.push({ status: "experiment_proposed", at: nowIso(), by: "Autoresearcher (simulated)", note: `proposal ${p.id}` }); } } });
    audit(projectId, { type: "agent", name: "Autoresearcher (simulated)" }, "proposal.created", { type: "experiment_proposal", id: p.id, label: p.title });
    return p;
  }),
  review: (projectId, proposalId, decision, reviewerId, note) => simulate("autoresearcher.review", () => {
    const a = store.db().approvals.find((x) => x.subjectType === "experiment_proposal" && x.subjectId === proposalId && x.decision === "pending");
    if (!a) throw new ServiceError("No pending approval exists for this proposal.", "conflict");
    if (a.requestedBy === reviewerId) throw new ServiceError("You cannot approve your own proposal.", "forbidden");
    assertMayDecide(projectId, a, reviewerId);
    applyDecision(projectId, { ...a, note }, decision, personName(projectId, reviewerId));
    store.mutate((db) => { const x = db.approvals.find((y) => y.id === a.id); if (x) { x.decision = decision; x.reviewerId = reviewerId; x.note = note; x.decidedAt = nowIso(); } });
    audit(projectId, { type: "human", name: personName(projectId, reviewerId) }, `proposal.${decision}`, { type: "experiment_proposal", id: proposalId, label: a.subjectLabel }, note);
    return store.db().proposals.find((p) => p.id === proposalId)!;
  }),
  followUps: (projectId, proposalId) => simulate("autoresearcher.followUps", () => store.db().proposals.find((p) => p.id === proposalId && p.projectId === projectId)?.followUpSuggestions ?? []),
};

function setTask(projectId: string, taskId: string, status: Task["status"], action: string): Task {
  store.mutate((db) => { const t = db.tasks.find((x) => x.id === taskId && x.projectId === projectId); if (!t) notFound("task", taskId); t.status = status; });
  const t = store.db().tasks.find((x) => x.id === taskId)!;
  audit(projectId, { type: "human", name: store.get().user.name }, action, { type: "task", id: taskId, label: t.title });
  return t;
}
export const mockConductor: ConductorService = {
  listTasks: (projectId) => simulate("conductor.listTasks", () => store.db().tasks.filter((t) => t.projectId === projectId)),
  pause: (projectId, taskId) => simulate("conductor.pause", () => setTask(projectId, taskId, "paused", "task.paused")),
  resume: (projectId, taskId) => simulate("conductor.resume", () => setTask(projectId, taskId, "queued", "task.resumed")),
  cancel: (projectId, taskId) => simulate("conductor.cancel", () => setTask(projectId, taskId, "cancelled", "task.cancelled")),
};

export const mockPacks: PackRegistry = {
  listPacks: () => simulate("packs.list", () => store.db().packs),
  listTemplates: (packId) => simulate("packs.templates", () => store.db().templates.filter((t) => !packId || t.packId === packId)),
  getTemplate: (templateId, version) => simulate("packs.getTemplate", () => store.db().templates.find((t) => t.id === templateId && (version === undefined || t.version === version)) ?? notFound("template", templateId)),
  checkCompatibility: (projectId, testDefinitionId, artifactVersionId) => simulate("packs.compat", () => {
    const db = store.db();
    const test = db.tests.find((t) => t.id === testDefinitionId) ?? notFound("test", testDefinitionId);
    const av = db.artifacts.filter((a) => a.projectId === projectId).flatMap((a) => a.versions).find((v) => v.id === artifactVersionId);
    const res: CompatibilityResult = { testDefinitionId, artifactVersionId, compatible: false, reasons: [], path: "run" };
    if (!av) { res.reasons.push("artifact version not found in this project"); res.path = "import_results"; return res; }
    if (test.kind === "imported") { res.reasons.push("Imported test: results are brought in, never executed here."); res.path = "import_results"; return res; }
    if (!test.runnable) { res.reasons.push(test.unsupportedReason ?? "No runner supports this test yet."); res.path = "adapter_needed"; return res; }
    res.compatible = true; res.reasons.push(`Supported by ${test.runner}.`); return res;
  }),
};

export const mockCairn: CairnService = {
  verify: (projectId, evidenceRecordId) => simulate("cairn.verify", () => {
    const e = store.db().evidence.find((x) => x.id === evidenceRecordId && x.projectId === projectId) ?? notFound("evidence record", evidenceRecordId);
    // Never fabricate: the mock only reports what the record already carries. Nothing is upgraded to cairn_verified here.
    if (e.integrity === "cairn_verified") return { integrity: e.integrity, result: e.verification.result, checker: e.verification.checker, notes: e.verification.notes };
    return { integrity: e.integrity === "imported" ? "imported" : "hashed", result: e.integrity === "imported" ? "not_run" : "passed", checker: null,
      notes: "Cairn is not connected. Result reflects the stored manifest hash only; no independent checker ran." };
  }),
};

const REFUSALS: Array<{ re: RegExp; subject: string; subjectType: "acceptance_criteria" | "settings_change" | "experiment_proposal" }> = [
  { re: /(acceptance|criteria|threshold|pass\s*\/?\s*fail|safety factor)/i, subject: "acceptance criteria", subjectType: "acceptance_criteria" },
  { re: /(permission|role|access|confidential|member)/i, subject: "permissions", subjectType: "settings_change" },
  { re: /(test definition|change the test|edit the test|runner|resource limit|budget)/i, subject: "test definitions", subjectType: "experiment_proposal" },
];
export const mockAssistant: AssistantService = {
  send: (projectId, viewConfig, text, user) => simulate("assistant.send", () => {
    const at = nowIso();
    const refusal = REFUSALS.find((r) => r.re.test(text));
    if (refusal) {
      const a: Approval = { id: newId("apr"), projectId, subjectType: refusal.subjectType, subjectId: `assistant-request-${Date.now()}`, subjectLabel: `Assistant-routed request: ${text.slice(0, 60)}`, requestedBy: user.id, requestedAt: at, decision: "pending", reviewerId: null, note: "", decidedAt: null, rationale: `The assistant may only change how views are configured. Changing ${refusal.subject} needs a reviewer's decision.` };
      store.mutate((db) => { db.approvals.unshift(a); });
      audit(projectId, { type: "agent", name: "Assistant (simulated)" }, "assistant.refused", { type: refusal.subjectType, id: a.id, label: a.subjectLabel }, text);
      const reply: AssistantMessage = { id: newId("msg"), role: "assistant", at, text: `I can't change ${refusal.subject} from here. The assistant only adjusts how views are configured (panels, ordering, filters, which supported tests are shown). I've created an approval request so a reviewer can decide: "${a.subjectLabel}".`, action: { kind: "refused", reason: `changes to ${refusal.subject} require an approval`, approvalRequestId: a.id } };
      return { reply, viewConfig };
    }
    const next: ViewConfig = { ...viewConfig, panelOrder: [...viewConfig.panelOrder], hiddenPanels: [...viewConfig.hiddenPanels], filters: { ...viewConfig.filters }, chosenTestIds: [...viewConfig.chosenTestIds] };
    let summary = "";
    const hide = /hide (the )?([a-z_ ]+?)( panel)?$/i.exec(text.trim());
    const show = /show (the )?([a-z_ ]+?)( panel)?$/i.exec(text.trim());
    const filter = /(only|filter)\s+(failed|passed|open|pending|completed)/i.exec(text);
    const top = /(move|put)\s+(the\s+)?([a-z_ ]+?)\s+(to the )?top/i.exec(text);
    const tests = /(only )?show (the )?tests? (matching|about|for|named) (.+)$/i.exec(text.trim());
    const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, "_");
    if (tests) {
      const needle = (tests[4] ?? "").toLowerCase().replace(/[".]/g, "").trim();
      const project = store.db().projects.find((p) => p.id === projectId);
      const matches = store.db().tests.filter((t) => t.packId === project?.packId && t.runnable && (t.name.toLowerCase().includes(needle) || t.description.toLowerCase().includes(needle)));
      next.chosenTestIds = matches.map((t) => t.id);
      summary = matches.length ? `Showing ${matches.length} supported test${matches.length === 1 ? "" : "s"} matching "${needle}" on the Tests page.` : `No supported test matches "${needle}"; the Tests page shows all tests.`;
    }
    else if (hide) { const id = norm(hide[2] ?? ""); if (!next.hiddenPanels.includes(id)) next.hiddenPanels.push(id); summary = `Hid the "${hide[2]}" panel.`; }
    else if (show) { const id = norm(show[2] ?? ""); next.hiddenPanels = next.hiddenPanels.filter((p) => p !== id); summary = `Showing the "${show[2]}" panel.`; }
    else if (filter) { next.filters["status"] = (filter[2] ?? "").toLowerCase(); summary = `Filtered lists to "${filter[2]}".`; }
    else if (top) { const id = norm(top[3] ?? ""); next.panelOrder = [id, ...next.panelOrder.filter((p) => p !== id)]; summary = `Moved "${top[3]}" to the top of the workspace.`; }
    else if (/reset (the )?(view|layout|filters)/i.test(text)) { next.panelOrder = []; next.hiddenPanels = []; next.filters = {}; next.chosenTestIds = []; summary = "Reset the view configuration to the template default."; }
    const reply: AssistantMessage = summary
      ? { id: newId("msg"), role: "assistant", at, text: `${summary} (View configuration only; nothing about the project's criteria, tests or permissions changed.)`, action: { kind: "view_change", summary } }
      : { id: newId("msg"), role: "assistant", at, text: "I can change how this workspace is shown: try \"hide the recent activity panel\", \"show the key metrics panel\", \"move next actions to the top\", \"only failed\", \"show tests matching latency\" or \"reset the view\". I can't change acceptance criteria, permissions or test definitions; those go to a reviewer." };
    if (summary) audit(projectId, { type: "agent", name: "Assistant (simulated)" }, "view.configured", { type: "view_config", id: projectId, label: summary }, text);
    return { reply, viewConfig: next };
  }),
};

export const mockLearning: LearningService = {
  listMemory: (projectId) => simulate("learning.memory", () => store.db().memory.filter((m) => m.projectId === projectId)),
  listAgentConfigChanges: (projectId) => simulate("learning.agentConfig", () => store.db().agentConfigChanges.filter((c) => c.projectId === projectId)),
  listModelTraining: () => simulate("learning.modelTraining", () => store.db().modelTraining),
};
