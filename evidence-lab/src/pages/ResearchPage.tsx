import { useState } from "react";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, MemberSwitcher, PageHeader, ProposalCard, QueryBoundary } from "@/components";
import { byId } from "@/lib/lookup";
import type { ExperimentProposal } from "@/contracts";

function ReviewControls({ proposal, projectId, onDone }: { proposal: ExperimentProposal; projectId: string; onDone: (m: string) => void }) {
  const user = useAppStore((s) => s.user);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function review(d: "approved" | "rejected" | "changes_requested") {
    setBusy(true); setErr(null);
    try { const r = await services.autoresearcher.review(projectId, proposal.id, d, user.id, note); onDone(`${r.title}: ${d.replace(/_/g, " ")}${d === "approved" ? ` as protocol v${r.protocolVersion}` : ""}.`); }
    catch (e) { setErr(e instanceof ServiceError ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return (
    <div className="w-full" data-testid="review-controls">
      <div className="h3 mb-1">Review (protocol approval)</div>
      <textarea className="input" rows={2} placeholder="Review note" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Review note" />
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => review("approved")} data-testid="proposal-approve">Approve as protocol v{proposal.protocolVersion + 1}</button>
        <button type="button" className="btn-danger btn-sm" disabled={busy || !note.trim()} onClick={() => review("rejected")}>Reject</button>
        <button type="button" className="btn-ghost btn-sm" disabled={busy || !note.trim()} onClick={() => review("changes_requested")}>Request changes</button>
      </div>
      {err ? <div className="callout-bad mt-2 text-xs" role="alert">{err}</div> : null}
    </div>
  );
}

export function ResearchPage() {
  const { project } = useProject();
  const q = useQuery(async () => ({ proposals: await services.autoresearcher.list(project.id), runs: await services.evidenceLab.listRuns(project.id), approvals: await services.approvals.list(project.id) }), [project.id]);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <>
      <PageHeader title="Research" subtitle="Experiment proposals from the Autoresearcher (simulated). A proposal runs only under an approved, numbered protocol; results link to runs; follow-ups are suggestions, never auto-executed." actions={<MemberSwitcher project={project} />} />
      {msg ? <div className="callout-ok mb-3 text-sm" role="status">{msg}</div> : null}
      <QueryBoundary q={q} label="Loading proposals">{({ proposals, runs, approvals }) => proposals.length === 0 ? <EmptyState title="No proposals yet" hint="Proposals are generated from findings and reviewed before anything runs." /> : (
        <div className="grid gap-4">{proposals.map((p) => { const pending = approvals.some((a) => a.subjectType === "experiment_proposal" && a.subjectId === p.id && a.decision === "pending"); return <ProposalCard key={p.id} proposal={p} runsById={byId(runs)} projectId={project.id} actions={pending ? <ReviewControls proposal={p} projectId={project.id} onDone={setMsg} /> : undefined} />; })}</div>
      )}</QueryBoundary>
      <div className="callout-sample mt-4 text-xs">The Autoresearcher is simulated: proposals here are sample data and the model label reads "sample-model (no real model connected)".</div>
    </>
  );
}
