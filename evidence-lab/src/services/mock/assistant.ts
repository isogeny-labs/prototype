/**
 * Simulated assistant: a rule-based advisor over the live sample records. No model is connected.
 *
 * Rules that a connected assistant must keep:
 *  - send() never mutates project data. It may change view configuration (audited) and it may draft actions.
 *  - Every drafted action is executed only by confirm(), which the UI calls on an explicit human click, as that human.
 *  - Acceptance criteria, permissions and test definitions are never changed directly: the assistant drafts a
 *    criteria version, a settings-change request or an experiment proposal, and the usual approval gates follow.
 *  - Execution is never started by the assistant on its own.
 */
import type { AssistantService } from "../types";
import { ServiceError } from "../types";
import { store } from "@/store";
import { simulate, nowIso, newId, notFound, audit } from "./base";
import type { Approval, AssistantContext, AssistantMessage, AssistantSuggestedAction, ExperimentProposal, Finding, Project, Run, Task, TestDefinition, ViewConfig } from "@/contracts";
import { canResolve, computeEvidenceLabel, toUserFacingStatus } from "@/contracts";
import { latestTargetVersion, supersededIds, versionLabel } from "@/lib/lookup";
import { mockEvidenceLab } from "./evidenceLab";
import { mockApprovals, mockAutoresearcher, mockConductor } from "./others";

const SIMULATED = "Simulated assistant: rule-based over the sample records; a connected model would reason over the same data. Nothing runs until you confirm.";

type Snapshot = {
  project: Project; runs: Run[]; sup: Set<string>; tests: TestDefinition[]; findings: Finding[]; approvals: Approval[]; proposals: ExperimentProposal[]; tasks: Task[];
  runsById: Record<string, Run>; myRole: string | null;
};
function snapshot(projectId: string, userId: string): Snapshot {
  const db = store.db();
  const project = db.projects.find((p) => p.id === projectId) ?? notFound("project", projectId);
  const runs = db.runs.filter((r) => r.projectId === projectId).sort((a, b) => a.sequence - b.sequence);
  return {
    project, runs, sup: supersededIds(runs), tests: db.tests.filter((t) => t.packId === project.packId), findings: db.findings.filter((f) => f.projectId === projectId),
    approvals: db.approvals.filter((a) => a.projectId === projectId), proposals: db.proposals.filter((p) => p.projectId === projectId), tasks: db.tasks.filter((t) => t.projectId === projectId),
    runsById: Object.fromEntries(runs.map((r) => [r.id, r])), myRole: project.permissions.members.find((m) => m.personId === userId)?.role ?? null,
  };
}
const S = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
const act = (kind: AssistantSuggestedAction["kind"], label: string, why: string, params: AssistantSuggestedAction["params"], gate: string | null, href?: string): AssistantSuggestedAction => ({ id: newId("act"), kind, label, why, params, gate, href });

/** Can this user decide this approval? Mirrors assertMayDecide in the approvals mock. */
function mayDecide(s: Snapshot, a: Approval): boolean {
  const db = store.db();
  const template = db.templates.find((t) => t.id === s.project.templateId && t.version === s.project.templateVersion);
  const required = template?.approvalGates.find((g) => g.subjectType === a.subjectType)?.requiredRole ?? "reviewer";
  const me = store.get().user.id;
  if (a.requestedBy === me) return false;
  return s.myRole === "owner" || (required === "reviewer" && s.myRole === "reviewer");
}

/* ---------------- analyses: each returns text + suggestions ---------------- */

function evidenceSummary(s: Snapshot): { text: string; suggestions: AssistantSuggestedAction[] } {
  const db = store.db();
  const live = s.runs.filter((r) => r.status === "completed" && !s.sup.has(r.id));
  const failedLive = live.filter((r) => r.overallPass === false);
  const labels = s.findings.map((f) => ({ f, label: computeEvidenceLabel(db.checks.filter((c) => f.checkIds.includes(c.id))), status: toUserFacingStatus(f, s.runsById) }));
  const byLabel = labels.reduce<Record<string, number>>((m, x) => ({ ...m, [x.label]: (m[x.label] ?? 0) + 1 }), {});
  const open = labels.filter((x) => !["Resolved within tested scope", "Not relevant"].includes(x.status));
  const weak = labels.filter((x) => x.label === "Estimate" || x.label === "Model-reviewed");
  const conflicts = s.findings.flatMap((f) => f.conflicts.filter((c) => !c.resolved).map((c) => ({ f, c })));
  const target = latestTargetVersion(s.project.packId, db.artifacts.filter((a) => a.projectId === s.project.id));
  const untested = s.tests.filter((t) => t.runnable && !live.some((r) => r.testDefinitionId === t.id && (!target || r.artifactVersionId === target.id)));
  const notRunnable = s.tests.filter((t) => !t.runnable);
  const lines = [
    `Evidence so far for ${s.project.name}: ${S(live.length, "completed, non-superseded run")} (${failedLive.length} failing criteria), ${S(s.findings.length, "finding")} (${Object.entries(byLabel).map(([k, v]) => `${v} ${k}`).join(", ") || "none"}), ${S(open.length, "unresolved finding")}.`,
    weak.length ? `Weakest claims: ${weak.map((x) => `${x.f.id} (${x.label})`).join(", ")}. Only a deterministic check or a named reviewer can raise them; agreement between agents cannot.` : "Every finding has at least a deterministic check or a reviewer behind it.",
    conflicts.length ? `Unresolved disagreements: ${conflicts.map(({ f, c }) => `${f.id}: ${c.summary}`).join(" ")}` : "No unresolved disagreements between agents or methods.",
    target ? `Latest artifact under test: ${target.artifactName} ${target.version}. ${untested.length ? `Not yet run on it: ${untested.map((t) => t.name).join("; ")}.` : "Every supported test has a run on it."}` : "",
    notRunnable.length ? `Cannot be run here: ${notRunnable.map((t) => t.name).join("; ")} (import results or request an adapter).` : "",
  ].filter(Boolean);
  const suggestions: AssistantSuggestedAction[] = [];
  for (const { f, c } of conflicts.slice(0, 2)) if (!c.investigationProposalId) suggestions.push(act("create_proposal", `Propose an experiment to settle the disagreement on ${f.id}`, c.summary, { findingId: f.id, affectedArtifactVersionId: f.artifactVersionIds[0] ?? "", prompt: c.summary }, "protocol approval by a reviewer"));
  for (const x of weak.slice(0, 2)) if (!x.f.conflicts.some((c) => c.investigationProposalId) && !suggestions.some((a) => a.params["findingId"] === x.f.id)) suggestions.push(act("create_proposal", `Propose an experiment to test ${x.f.id} deterministically`, `${x.f.id} is only ${x.label}; a bounded experiment with a deterministic check could raise it.`, { findingId: x.f.id, affectedArtifactVersionId: x.f.artifactVersionIds[0] ?? "", prompt: x.f.statement }, "protocol approval by a reviewer"));
  if (target) for (const t of untested.slice(0, 3)) suggestions.push(act("request_run", `Request ${t.name} on ${target.artifactName} ${target.version}`, `Supported test with no completed run on the latest artifact version.`, { testDefinitionId: t.id, artifactVersionId: target.id }, t.kind === "proposed" ? "execution approval by a reviewer" : "execution approval"));
  return { text: lines.join("\n"), suggestions };
}

function nextExperiments(s: Snapshot): { text: string; suggestions: AssistantSuggestedAction[] } {
  const base = evidenceSummary(s);
  const followUps = s.proposals.flatMap((p) => p.followUpSuggestions.map((f) => ({ p, f })));
  const suggestions = [...base.suggestions.filter((a) => a.kind === "create_proposal")];
  for (const { p, f } of followUps.slice(0, 3)) suggestions.push(act("create_proposal", `Propose: ${f.slice(0, 70)}${f.length > 70 ? "…" : ""}`, `Follow-up suggested after ${p.title}; it becomes a new proposal needing its own protocol approval.`, { findingId: p.findingId, affectedArtifactVersionId: p.affectedArtifactVersionId, prompt: f }, "protocol approval by a reviewer"));
  for (const a of base.suggestions.filter((x) => x.kind === "request_run")) suggestions.push(a);
  const text = suggestions.length
    ? `Where the evidence is thinnest, and what would strengthen it:\n${suggestions.map((a, i) => `${i + 1}. ${a.label}. ${a.why}`).join("\n")}\nEach of these is a draft: confirm one and it is created as you, then a reviewer approves the protocol or the execution.`
    : "I do not see an obvious next experiment: no unresolved disagreements, no Estimate-only findings, and every supported test has a run on the latest artifact. Consider the tests that cannot run here, which need imported results or an adapter.";
  return { text, suggestions: suggestions.slice(0, 6) };
}

function orchestration(s: Snapshot): { text: string; suggestions: AssistantSuggestedAction[] } {
  const by = (st: Task["status"]) => s.tasks.filter((t) => t.status === st);
  const blocked = by("blocked"), waiting = by("awaiting_checkpoint"), paused = by("paused"), queued = by("queued"), running = by("running");
  const hot = s.tasks.filter((t) => t.budget.limit > 0 && t.budget.used / t.budget.limit >= 0.9 && t.status !== "done");
  const lines = [
    `Orchestration: ${S(s.tasks.length, "task")}; ${by("done").length} done, ${running.length} running, ${queued.length} queued, ${waiting.length} at a checkpoint, ${paused.length} paused, ${blocked.length} blocked.`,
    waiting.length ? `At a checkpoint: ${waiting.map((t) => `${t.title} (${t.checkpoint?.label ?? "checkpoint"})`).join("; ")}. The owner decides on the Approvals page; nothing proceeds until then.` : "",
    blocked.length ? `Blocked: ${blocked.map((t) => `${t.title}: ${t.note ?? "no note"}`).join("; ")}` : "",
    hot.length ? `Near budget: ${hot.map((t) => `${t.title} (${t.budget.used}/${t.budget.limit} ${t.budget.unit.replace(/_/g, " ")})`).join("; ")}` : "No task is near its budget.",
    `Owners: ${S(s.tasks.filter((t) => t.owner.type === "agent").length, "agent task")}, ${S(s.tasks.filter((t) => t.owner.type === "tool").length, "tool task")}, ${S(s.tasks.filter((t) => t.owner.type === "human").length, "human task")}. Agent and tool owners are simulated.`,
  ].filter(Boolean);
  const suggestions: AssistantSuggestedAction[] = [];
  for (const t of waiting) { const a = t.checkpoint ? s.approvals.find((x) => x.id === t.checkpoint?.approvalId) : undefined; if (a && a.decision === "pending") suggestions.push(mayDecide(s, a) ? act("decide_approval", `Approve the checkpoint for "${t.title}"`, `${a.rationale} You are ${s.myRole} here and may decide.`, { approvalId: a.id, decision: "approved", note: "Approved via assistant suggestion" }, null) : act("navigate", `Open the checkpoint approval for "${t.title}"`, `${a.rationale} Your role (${s.myRole ?? "not a member"}) cannot decide it; the owner can.`, {}, "owner approval", `/p/${s.project.id}/approvals`)); }
  for (const t of paused) suggestions.push(act("resume_task", `Resume "${t.title}"`, "Paused; resuming re-queues it (simulated Conductor).", { taskId: t.id }, null));
  for (const t of blocked) suggestions.push(act("cancel_task", `Cancel "${t.title}"`, `${t.note ?? "Blocked"}. Cancelling keeps the plan honest; it can be re-planned once the capability exists.`, { taskId: t.id }, null));
  for (const t of running) suggestions.push(act("pause_task", `Pause "${t.title}"`, "Running; pausing stops budget use until resumed.", { taskId: t.id }, null));
  return { text: lines.join("\n"), suggestions: suggestions.slice(0, 5) };
}

function executions(s: Snapshot): { text: string; suggestions: AssistantSuggestedAction[] } {
  const failed = s.runs.filter((r) => r.status === "failed" && !s.sup.has(r.id));
  const awaiting = s.runs.filter((r) => r.status === "awaiting_approval");
  const queued = s.runs.filter((r) => r.status === "queued");
  const failingCriteria = s.runs.filter((r) => r.status === "completed" && !s.sup.has(r.id) && r.overallPass === false);
  const lines = [
    `Executions: ${S(s.runs.length, "run")} (${s.sup.size} superseded), ${awaiting.length} awaiting approval, ${queued.length} queued, ${failed.length} failed without a retry, ${failingCriteria.length} completed with failing criteria.`,
    failingCriteria.length ? `Failing criteria: ${failingCriteria.map((r) => `#${r.sequence} ${s.tests.find((t) => t.id === r.testDefinitionId)?.name ?? r.testDefinitionId} on ${versionLabel(store.db().artifacts, r.artifactVersionId)}`).join("; ")}.` : "",
    failed.length ? `Failed runs: ${failed.map((r) => `#${r.sequence} (${r.failures[0] ?? "no reason recorded"})`).join("; ")}.` : "",
    "I never start a run myself: confirm a request and it is created as you, then execution approval applies where the template requires it.",
  ].filter(Boolean);
  const suggestions: AssistantSuggestedAction[] = [];
  for (const r of failed) suggestions.push(act("retry_run", `Retry run #${r.sequence} as a new run`, `${r.failures[0] ?? "Failed"}. A retry is a new append-only record that supersedes #${r.sequence}.`, { runId: r.id }, null));
  for (const r of awaiting) { const a = r.approvalId ? s.approvals.find((x) => x.id === r.approvalId) : undefined; if (a && a.decision === "pending") suggestions.push(mayDecide(s, a) ? act("decide_approval", `Approve execution of run #${r.sequence}`, a.rationale, { approvalId: a.id, decision: "approved", note: "Approved via assistant suggestion" }, null) : act("navigate", `Open the execution approval for run #${r.sequence}`, `Your role (${s.myRole ?? "not a member"}) cannot decide it, or you requested it.`, {}, "execution approval", `/p/${s.project.id}/approvals`)); }
  for (const f of s.findings) if (f.revisedArtifactVersionId && f.retestRunIds.length === 0) { const r = s.runs.filter((x) => f.evidenceRunIds.includes(x.id)).sort((a, b) => b.sequence - a.sequence)[0]; const t = r ? s.tests.find((x) => x.id === r.testDefinitionId) : undefined; if (t?.runnable) suggestions.push(act("request_run", `Request a retest of ${t.name} on the revised artifact for ${f.id}`, "An external change was reported but no retest is linked yet.", { testDefinitionId: t.id, artifactVersionId: f.revisedArtifactVersionId }, "execution approval")); }
  return { text: lines.join("\n"), suggestions: suggestions.slice(0, 5) };
}

function research(s: Snapshot): { text: string; suggestions: AssistantSuggestedAction[] } {
  const pending = s.proposals.filter((p) => s.approvals.some((a) => a.subjectType === "experiment_proposal" && a.subjectId === p.id && a.decision === "pending"));
  const lines = [
    `Autoresearcher (simulated): ${S(s.proposals.length, "proposal")}: ${s.proposals.map((p) => `${p.title} (${p.status}, protocol v${p.protocolVersion}${p.resultRunIds.length ? `, ${S(p.resultRunIds.length, "result run")}` : ""})`).join("; ") || "none"}.`,
    pending.length ? `Awaiting protocol approval: ${pending.map((p) => p.title).join("; ")}. Approving freezes a numbered protocol; amendments never overwrite earlier results.` : "No proposal is waiting for review.",
    ...s.proposals.filter((p) => p.resultSummary).map((p) => `Result of "${p.title}": ${p.resultSummary}`),
  ];
  const suggestions: AssistantSuggestedAction[] = [];
  for (const p of pending) { const a = s.approvals.find((x) => x.subjectType === "experiment_proposal" && x.subjectId === p.id && x.decision === "pending")!; suggestions.push(mayDecide(s, a) ? act("review_proposal", `Approve "${p.title}" as protocol v${p.protocolVersion + 1}`, `Hypothesis: ${p.hypothesis} Budget ${p.budget.computeUnits} compute units, ${p.budget.timeHours} h.`, { proposalId: p.id, decision: "approved", note: "Approved via assistant suggestion" }, null) : act("navigate", `Open "${p.title}" for review`, `Your role (${s.myRole ?? "not a member"}) cannot approve protocols; a reviewer or the owner can.`, {}, "protocol approval", `/p/${s.project.id}/research`)); }
  const nx = nextExperiments(s); for (const a of nx.suggestions.filter((x) => x.kind === "create_proposal").slice(0, 3)) suggestions.push(a);
  return { text: lines.join("\n"), suggestions: suggestions.slice(0, 6) };
}

function pendingForMe(s: Snapshot): { text: string; suggestions: AssistantSuggestedAction[] } {
  const pending = s.approvals.filter((a) => a.decision === "pending");
  const mine = pending.filter((a) => mayDecide(s, a));
  const lines = [
    `${S(pending.length, "pending approval")}; ${mine.length} you can decide as ${s.myRole ?? "a non-member"}: ${mine.map((a) => a.subjectLabel).join("; ") || "none"}.`,
    pending.length > mine.length ? `Not yours to decide: ${pending.filter((a) => !mine.includes(a)).map((a) => `${a.subjectLabel} (${a.requestedBy === store.get().user.id ? "you requested it" : "needs a different role"})`).join("; ")}.` : "",
  ].filter(Boolean);
  const suggestions: AssistantSuggestedAction[] = [];
  for (const a of mine.slice(0, 4)) {
    const resolvable = a.subjectType === "finding_resolution" ? canResolve(s.findings.find((f) => f.id === a.subjectId)!, s.runsById) : { ok: true, reason: "" };
    if (!resolvable.ok) suggestions.push(act("navigate", `Review "${a.subjectLabel}" (cannot be approved yet)`, `${resolvable.reason} Approving would be refused.`, {}, null, `/p/${s.project.id}/approvals`));
    else suggestions.push(act("decide_approval", `Approve: ${a.subjectLabel}`, a.rationale, { approvalId: a.id, decision: "approved", note: "Approved via assistant suggestion" }, null));
  }
  for (const f of s.findings) if (canResolve(f, s.runsById).ok && f.status !== "closed" && !pending.some((a) => a.subjectType === "finding_resolution" && a.subjectId === f.id)) suggestions.push(act("request_resolution", `Request resolution of ${f.id}`, canResolve(f, s.runsById).reason, { findingId: f.id, label: `Resolve finding ${f.id} within tested scope` }, "reviewer approval"));
  return { text: lines.join("\n"), suggestions: suggestions.slice(0, 6) };
}

function findingsBrief(s: Snapshot, entityId?: string): { text: string; suggestions: AssistantSuggestedAction[] } {
  const db = store.db();
  const subset = entityId ? s.findings.filter((f) => f.id === entityId) : s.findings;
  const lines = subset.map((f) => {
    const checks = db.checks.filter((c) => f.checkIds.includes(c.id));
    const label = computeEvidenceLabel(checks);
    return `${f.id} [${label}, ${toUserFacingStatus(f, s.runsById)}]: ${f.statement} Checks: ${checks.map((c) => c.kind.replace(/_/g, " ")).join(", ") || "none"}. Limits: ${f.limitations[0] ?? "none stated"}`;
  });
  const sug = pendingForMe(s).suggestions.filter((a) => !entityId || String(a.params["findingId"] ?? "").includes(entityId) || a.label.includes(entityId));
  const ev = evidenceSummary(s).suggestions.filter((a) => !entityId || a.params["findingId"] === entityId);
  return { text: lines.join("\n") || "No findings yet.", suggestions: [...sug, ...ev].slice(0, 5) };
}

/* ---------------- guarded requests: draft, never change ---------------- */

function guarded(s: Snapshot, text: string): { reply: AssistantMessage } | null {
  const at = nowIso();
  const base = (t: string, suggestions: AssistantSuggestedAction[], reason: string): { reply: AssistantMessage } => ({ reply: { id: newId("msg"), role: "assistant", at, text: t, action: { kind: "refused", reason, approvalRequestId: null }, suggestions } });
  if (/(acceptance|criteria|threshold|pass\s*\/?\s*fail|safety factor)/i.test(text) && /(change|set|lower|raise|make|update|edit|relax|tighten)/i.test(text)) {
    const crit = store.db().criteria.filter((c) => c.projectId === s.project.id).sort((a, b) => b.version - a.version)[0];
    const num = /(-?\d+(?:\.\d+)?)/.exec(text.replace(/\bv\d+\b/g, ""));
    const words = text.toLowerCase();
    const item = crit?.items.find((i) => (i.metric && words.includes(i.metric.split("_")[0] ?? "")) || i.text.toLowerCase().split(/\W+/).some((w) => w.length > 5 && words.includes(w)));
    if (crit && item && num) {
      const items = crit.items.map((i) => (i.id === item.id ? { ...i, threshold: Number(num[1]) } : i));
      return base(`I can't change acceptance criteria directly: every run is judged against an approved version. I can draft version ${crit.version + 1} with ${item.id} set to ${item.operator ?? ""} ${num[1]}${item.unit ? ` ${item.unit}` : ""}; the project owner must approve it, and v${crit.version} stays in force until then.`,
        [act("propose_criteria", `Draft acceptance criteria v${crit.version + 1}: ${item.id} → ${num[1]}${item.unit ? ` ${item.unit}` : ""}`, `Changes ${item.text}`, { items: items as unknown as Array<Record<string, unknown>> }, "owner approval")], "acceptance criteria are versioned and owner-approved");
    }
    return base("I can't change acceptance criteria directly. Tell me which criterion and the new threshold (for example \"set the latency threshold to 3 ms\") and I will draft a new version for the owner's approval, or use the form on the Intake page.", [act("navigate", "Open Intake to propose a new criteria version", "The form proposes a version; it never edits the current one.", {}, "owner approval", `/p/${s.project.id}/intake`)], "acceptance criteria are versioned and owner-approved");
  }
  if (/(permission|role|access|confidential|member)/i.test(text) && /(change|set|give|grant|make|add|remove|revoke|update)/i.test(text)) {
    return base("I can't change permissions or membership. I can draft a settings-change request for the owner to decide.", [act("request_settings_change", "Draft a settings-change request for the owner", text, { label: `Settings change: ${text.slice(0, 80)}` }, "owner approval")], "permissions change only through an owner-approved settings change");
  }
  if (/(test definition|change the test|edit the test|runner|resource limit)/i.test(text) && /(change|edit|set|update|modify|increase|decrease)/i.test(text)) {
    const target = latestTargetVersion(s.project.packId, store.db().artifacts.filter((a) => a.projectId === s.project.id));
    return base("I can't edit test definitions: they are versioned records. What I can do is draft an experiment proposal that defines a new protocol; a reviewer approves it before anything runs.", target ? [act("create_proposal", "Draft an experiment proposal for this instead", text, { findingId: null, affectedArtifactVersionId: target.id, prompt: text }, "protocol approval by a reviewer")] : [], "test definitions are versioned; changes go through a proposal");
  }
  return null;
}

/* ---------------- view commands (unchanged behaviour) ---------------- */

function viewCommand(projectId: string, viewConfig: ViewConfig, text: string): { summary: string; next: ViewConfig } | null {
  const next: ViewConfig = { ...viewConfig, panelOrder: [...viewConfig.panelOrder], hiddenPanels: [...viewConfig.hiddenPanels], filters: { ...viewConfig.filters }, chosenTestIds: [...viewConfig.chosenTestIds] };
  const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, "_");
  const tests = /(only )?show (the )?tests? (matching|about|for|named) (.+)$/i.exec(text.trim());
  const hide = /^hide (the )?([a-z_ ]+?)( panel)?$/i.exec(text.trim());
  const show = /^show (the )?([a-z_ ]+?)( panel)?$/i.exec(text.trim());
  const filter = /^(only|filter)\s+(failed|passed|open|pending|completed)$/i.exec(text.trim());
  const top = /(move|put)\s+(the\s+)?([a-z_ ]+?)\s+(to the )?top/i.exec(text);
  if (tests) {
    const needle = (tests[4] ?? "").toLowerCase().replace(/[".]/g, "").trim();
    const project = store.db().projects.find((p) => p.id === projectId);
    const matches = store.db().tests.filter((t) => t.packId === project?.packId && t.runnable && (t.name.toLowerCase().includes(needle) || t.description.toLowerCase().includes(needle)));
    next.chosenTestIds = matches.map((t) => t.id);
    return { summary: matches.length ? `Showing ${matches.length} supported test${matches.length === 1 ? "" : "s"} matching "${needle}" on the Tests page.` : `No supported test matches "${needle}"; the Tests page shows all tests.`, next };
  }
  if (hide) { const id = norm(hide[2] ?? ""); if (!next.hiddenPanels.includes(id)) next.hiddenPanels.push(id); return { summary: `Hid the "${hide[2]}" panel.`, next }; }
  if (show) { const id = norm(show[2] ?? ""); next.hiddenPanels = next.hiddenPanels.filter((p) => p !== id); return { summary: `Showing the "${show[2]}" panel.`, next }; }
  if (filter) { next.filters["status"] = (filter[2] ?? "").toLowerCase(); return { summary: `Filtered lists to "${filter[2]}".`, next }; }
  if (top) { const id = norm(top[3] ?? ""); next.panelOrder = [id, ...next.panelOrder.filter((p) => p !== id)]; return { summary: `Moved "${top[3]}" to the top of the workspace.`, next }; }
  if (/reset (the )?(view|layout|filters)/i.test(text)) { next.panelOrder = []; next.hiddenPanels = []; next.filters = {}; next.chosenTestIds = []; return { summary: "Reset the view configuration to the template default.", next }; }
  return null;
}

/* ---------------- routing ---------------- */

function analyse(s: Snapshot, text: string, ctx: AssistantContext): { text: string; suggestions: AssistantSuggestedAction[] } {
  const t = text.toLowerCase();
  if (/(help|what can you do|capabilit)/.test(t)) return { text: "I read this project's records and can: summarise the evidence; say where it is thinnest and propose experiments; review orchestration (tasks, budgets, checkpoints); review executions (failed, queued, awaiting approval); review Autoresearcher proposals; list what is waiting on you; and change how views are laid out. Anything that changes the project appears as a card you confirm; approval gates then apply. I never start a run, approve anything, or change criteria, permissions or tests on my own.", suggestions: [] };
  if (/(orchestrat|conductor|\btasks?\b|budget|checkpoint)/.test(t)) return orchestration(s);
  if (/(proposal|autoresearch|protocol|research)/.test(t)) return research(s);
  if (/(waiting on me|pending|approv|decide|what do i need to do|my queue)/.test(t)) return pendingForMe(s);
  if (/(next|should we|suggest|experiment|brainstorm|idea|strengthen|where.*(thin|weak))/.test(t)) return nextExperiments(s);
  if (/(execution|\bruns?\b|retest|retry|queued|failed run)/.test(t)) return executions(s);
  if (/(finding|label|conflict|disagree|claim)/.test(t)) return findingsBrief(s, ctx.page === "finding" ? ctx.entityId : undefined);
  if (/(summar|overview|status|where are we|evidence|how are we|what do we know)/.test(t)) return ctx.page === "finding" ? findingsBrief(s, ctx.entityId) : evidenceSummary(s);
  switch (ctx.page) {
    case "conductor": return orchestration(s);
    case "research": return research(s);
    case "runs": case "run": case "tests": return executions(s);
    case "approvals": return pendingForMe(s);
    case "findings": case "finding": return findingsBrief(s, ctx.page === "finding" ? ctx.entityId : undefined);
    default: return evidenceSummary(s);
  }
}

export const mockAssistant: AssistantService = {
  send: (projectId, viewConfig, text, user, context) => simulate("assistant.send", () => {
    const at = nowIso();
    const s = snapshot(projectId, user.id);
    const g = guarded(s, text);
    if (g) { audit(projectId, { type: "agent", name: "Assistant (simulated)" }, "assistant.refused", { type: "assistant", id: projectId, label: text.slice(0, 60) }, g.reply.action?.kind === "refused" ? g.reply.action.reason : undefined); return { reply: { ...g.reply, context }, viewConfig }; }
    const v = viewCommand(projectId, viewConfig, text);
    if (v) {
      audit(projectId, { type: "agent", name: "Assistant (simulated)" }, "view.configured", { type: "view_config", id: projectId, label: v.summary }, text);
      return { reply: { id: newId("msg"), role: "assistant", at, text: `${v.summary} (View configuration only; nothing about the project's criteria, tests or permissions changed.)`, action: { kind: "view_change", summary: v.summary }, context }, viewConfig: v.next };
    }
    const a = analyse(s, text, context);
    return { reply: { id: newId("msg"), role: "assistant", at, text: `${a.text}\n\n${SIMULATED}`, suggestions: a.suggestions, context }, viewConfig };
  }),
  confirm: (projectId, action, user) => simulate("assistant.confirm", async () => {
    const at = nowIso();
    const p = action.params;
    const str = (k: string) => String(p[k] ?? "");
    let summary: string;
    switch (action.kind) {
      case "request_run": { const r = await mockEvidenceLab.requestRun(projectId, { artifactVersionId: str("artifactVersionId"), testDefinitionId: str("testDefinitionId"), requestedBy: user.id }); summary = `Run #${r.sequence} requested by ${user.name}; it awaits execution approval. Nothing has executed.`; break; }
      case "retry_run": { const r = await mockEvidenceLab.retryRun(projectId, str("runId"), user.id); summary = `Run #${r.sequence} queued as a retry (new append-only record) by ${user.name}.`; break; }
      case "create_proposal": { const pr = await mockAutoresearcher.create(projectId, { findingId: p["findingId"] ? str("findingId") : null, affectedArtifactVersionId: str("affectedArtifactVersionId"), prompt: str("prompt") }); summary = `Proposal "${pr.title}" created; it needs protocol approval by a reviewer before anything runs.`; break; }
      case "review_proposal": { const pr = await mockAutoresearcher.review(projectId, str("proposalId"), str("decision") as "approved" | "rejected" | "changes_requested", user.id, str("note")); summary = `Proposal "${pr.title}": ${str("decision").replace(/_/g, " ")} by ${user.name}${pr.status === "approved" ? ` as protocol v${pr.protocolVersion}` : ""}.`; break; }
      case "decide_approval": { const a = await mockApprovals.decide(projectId, str("approvalId"), str("decision") as "approved" | "rejected" | "changes_requested", user.id, str("note")); summary = `${a.subjectLabel}: ${a.decision.replace(/_/g, " ")} by ${user.name}.`; break; }
      case "request_resolution": { await mockApprovals.request(projectId, { projectId, subjectType: "finding_resolution", subjectId: str("findingId"), subjectLabel: str("label"), requestedBy: user.id, rationale: "A finding is resolved only with a linked passing retest and a reviewer decision." }); summary = `Resolution of ${str("findingId")} requested by ${user.name}; a different reviewer decides.`; break; }
      case "propose_criteria": { const r = await mockEvidenceLab.proposeCriteriaVersion(projectId, p["items"] as unknown as Parameters<typeof mockEvidenceLab.proposeCriteriaVersion>[1], user.id); summary = `Acceptance criteria v${r.criteria.version} proposed by ${user.name}; the owner must approve it. v${r.criteria.version - 1} stays in force.`; break; }
      case "request_settings_change": { await mockApprovals.request(projectId, { projectId, subjectType: "settings_change", subjectId: projectId, subjectLabel: str("label"), requestedBy: user.id, rationale: "Confidentiality, membership and permission changes need the owner's approval." }); summary = `Settings-change request filed by ${user.name} for the owner to decide.`; break; }
      case "pause_task": { const t = await mockConductor.pause(projectId, str("taskId")); summary = `Paused "${t.title}" (simulated Conductor).`; break; }
      case "resume_task": { const t = await mockConductor.resume(projectId, str("taskId")); summary = `Resumed "${t.title}" (simulated Conductor).`; break; }
      case "cancel_task": { const t = await mockConductor.cancel(projectId, str("taskId")); summary = `Cancelled "${t.title}" (simulated Conductor).`; break; }
      case "navigate": summary = `Opened ${action.href ?? "the page"}.`; break;
      default: throw new ServiceError(`Unknown action ${String(action.kind)}`, "validation");
    }
    audit(projectId, { type: "human", name: user.name }, "assistant.action_confirmed", { type: action.kind, id: null, label: action.label }, summary);
    return { reply: { id: newId("msg"), role: "assistant", at, text: summary, action: { kind: "confirmed", summary } } };
  }),
};
