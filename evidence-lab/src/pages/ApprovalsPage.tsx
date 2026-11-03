import { useState } from "react";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import { ApprovalCard, EmptyState, MemberSwitcher, PageHeader, QueryBoundary } from "@/components";
import type { Approval } from "@/contracts";

type Decision = "approved" | "rejected" | "changes_requested";

function DecisionControls({ approval, projectId, onDone }: { approval: Approval; projectId: string; onDone: (msg: { kind: "ok" | "bad"; text: string }) => void }) {
  const user = useAppStore((s) => s.user);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<Decision | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const isRequester = approval.requestedBy === user.id;
  async function decide(d: Decision) {
    setBusy(d); setErr(null);
    try {
      const r = await services.approvals.decide(projectId, approval.id, d, user.id, note);
      onDone({ kind: "ok", text: `${r.subjectLabel}: ${d.replace(/_/g, " ")} by ${user.name}. The subject's status and history were updated.` });
    } catch (e) { const m = e instanceof ServiceError ? `${e.message}` : String(e); setErr(m); onDone({ kind: "bad", text: m }); }
    finally { setBusy(null); }
  }
  return (
    <div className="w-full" data-testid="decision-controls">
      {isRequester ? <div className="callout mb-2 text-xs" data-testid="self-approval-note">You requested this, so you cannot decide it (separation of duties). Switch the acting user to a reviewer or the owner to decide.</div> : null}
      <textarea className="input" rows={2} placeholder="Decision note (required for reject and request changes)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Decision note" data-testid="decision-note" />
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => decide("approved")} data-testid="approve">{busy === "approved" ? "Approving…" : "Approve"}</button>
        <button type="button" className="btn-danger btn-sm" disabled={busy !== null || !note.trim()} onClick={() => decide("rejected")} data-testid="reject">Reject</button>
        <button type="button" className="btn-ghost btn-sm" disabled={busy !== null || !note.trim()} onClick={() => decide("changes_requested")} data-testid="request-changes">Request changes</button>
      </div>
      {err ? <div className="callout-bad mt-2 text-xs" role="alert" data-testid="decision-error">{err}</div> : null}
    </div>
  );
}

export function ApprovalsPage() {
  const { project, template } = useProject();
  const q = useQuery(() => services.approvals.list(project.id), [project.id]);
  const [msg, setMsg] = useState<{ kind: "ok" | "bad"; text: string } | null>(null);
  return (
    <>
      <PageHeader title="Approvals" subtitle="Every decision is a record with who, when and why. Requesters cannot decide their own requests; the template's gates say which role decides. Decisions update the subject's status and history." actions={<MemberSwitcher project={project} />} />
      {msg ? <div className={`${msg.kind === "ok" ? "callout-ok" : "callout-bad"} mb-3 text-sm`} role="status" data-testid="approvals-message">{msg.text}</div> : null}
      <QueryBoundary q={q} label="Loading approvals">{(approvals) => {
        const pending = approvals.filter((a) => a.decision === "pending");
        const decided = approvals.filter((a) => a.decision !== "pending").sort((a, b) => ((a.decidedAt ?? "") < (b.decidedAt ?? "") ? 1 : -1));
        return (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <div>
              <h2 className="h3 mb-2">Pending ({pending.length})</h2>
              {pending.length === 0 ? <EmptyState title="Nothing pending" hint="Requests arrive from runs, proposals, recommendations, finding resolutions, checkpoints and the assistant." /> : <div className="grid gap-3">{pending.map((a) => <ApprovalCard key={a.id} approval={a} project={project} actions={<DecisionControls approval={a} projectId={project.id} onDone={setMsg} />} />)}</div>}
              <h2 className="h3 mb-2 mt-6">Decided ({decided.length})</h2>
              {decided.length === 0 ? <EmptyState title="No decisions yet" /> : <div className="grid gap-3">{decided.map((a) => <ApprovalCard key={a.id} approval={a} project={project} />)}</div>}
            </div>
            <aside className="panel text-sm self-start">
              <h2 className="h2 mb-2">Approval gates in {template.name} v{template.version}</h2>
              <ul className="space-y-2">{template.approvalGates.map((g) => <li key={g.id}><div className="font-medium">{g.subjectType.replace(/_/g, " ")} <span className="tag ml-1">{g.requiredRole}</span></div><div className="text-muted">{g.description}</div></li>)}</ul>
              <div className="mt-3 text-xs text-faint">Owners may decide any gate; reviewers decide reviewer-gated subjects; editors and viewers cannot decide. A finding cannot be resolved without a linked passing retest, whoever decides.</div>
            </aside>
          </div>
        );
      }}</QueryBoundary>
    </>
  );
}
