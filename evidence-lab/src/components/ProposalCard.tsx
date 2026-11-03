import { useState } from "react";
import { Link } from "react-router-dom";
import type { ExperimentProposal, Run } from "@/contracts";
import { fmtDateTime, humanize } from "@/lib/format";
import { Marker } from "./Marker";

const STATUS: Record<ExperimentProposal["status"], string> = {
  proposed: "border-warn/60 text-warn", under_review: "border-info/60 text-info", approved: "border-ok/60 text-ok",
  rejected: "border-bad/60 text-bad", executed: "border-accent/60 text-accent", reviewed: "border-accent/60 text-accent",
};

export function ProposalCard({ proposal, runsById, projectId, actions }: { proposal: ExperimentProposal; runsById: Record<string, Run>; projectId: string; actions?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="panel text-sm" data-testid="proposal-card" data-status={proposal.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`tag ${STATUS[proposal.status]}`}>{humanize(proposal.status)}</span>
        <span className="tag" title="Approvals freeze a numbered protocol version. 0 means not yet approved.">Protocol v{proposal.protocolVersion}</span>
        {proposal.proposedBy.type === "agent" ? <Marker kind="simulated" /> : null}
        <span className="ml-auto text-xs text-faint">{fmtDateTime(proposal.createdAt)}</span>
      </div>
      <h3 className="mt-2 font-semibold">{proposal.title}</h3>
      <div className="mt-1 text-xs text-muted">Proposed by {proposal.proposedBy.name}{proposal.proposedBy.model ? ` · model: ${proposal.proposedBy.model}` : ""}</div>
      <dl className="kv mt-3">
        <dt>Research question</dt><dd>{proposal.researchQuestion}</dd>
        <dt>Hypothesis</dt><dd>{proposal.hypothesis}</dd>
        <dt>Would establish</dt><dd>{proposal.wouldEstablish}</dd>
        <dt>Would not establish</dt><dd className="text-muted">{proposal.wouldNotEstablish}</dd>
        <dt>Budget</dt><dd>{proposal.budget.computeUnits} compute units · {proposal.budget.timeHours} h · ${proposal.budget.moneyUsd}</dd>
      </dl>
      <button type="button" className="btn-ghost btn-sm mt-3" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Hide" : "Show"} full protocol</button>
      {open ? (
        <dl className="kv mt-3 border-t border-line pt-3">
          <dt>Motivation</dt><dd>{proposal.motivation}</dd>
          <dt>Sources</dt><dd><ul className="list-disc pl-4">{proposal.sourceReferences.map((s) => <li key={`${s.kind}-${s.id}`}>{s.label} <span className="text-faint">({s.kind})</span></li>)}</ul></dd>
          <dt>Baseline and controls</dt><dd>{proposal.baselineAndControls}</dd>
          <dt>Procedure</dt><dd>{proposal.procedure}</dd>
          <dt>Outcome: success</dt><dd>{proposal.outcomes.success}</dd>
          <dt>Outcome: failure</dt><dd>{proposal.outcomes.failure}</dd>
          <dt>Outcome: inconclusive</dt><dd>{proposal.outcomes.inconclusive}</dd>
          <dt>Required artifacts</dt><dd>{proposal.requiredArtifacts.join("; ")}</dd>
          <dt>Safety boundaries</dt><dd>{proposal.safetyBoundaries}</dd>
          <dt>Protocol history</dt><dd>{proposal.protocolHistory.length === 0 ? <span className="text-faint">No approved version yet.</span> : <ul className="list-disc pl-4">{proposal.protocolHistory.map((h) => <li key={h.version}>v{h.version} · {fmtDateTime(h.at)} · {h.note} <span className="text-faint">({h.approvalId})</span></li>)}</ul>}</dd>
        </dl>
      ) : null}
      {(proposal.resultRunIds.length > 0 || proposal.resultSummary) ? (
        <div className="mt-3 border-t border-line pt-3">
          <div className="h3">Results</div>
          <div className="mt-1">{proposal.resultSummary || <span className="text-faint">No results yet.</span>}</div>
          <div className="mt-1 flex flex-wrap gap-2">{proposal.resultRunIds.map((id) => { const r = runsById[id]; return r ? <Link key={id} className="tag" to={`/p/${projectId}/runs/${id}`}>Run #{r.sequence}</Link> : <span key={id} className="tag">{id}</span>; })}</div>
          {proposal.followUpSuggestions.length > 0 ? (<div className="mt-2"><div className="h3">Follow-up suggestions <span className="normal-case text-faint">(suggestions only; each needs its own approved protocol)</span></div><ul className="mt-1 list-disc pl-4 text-muted">{proposal.followUpSuggestions.map((f) => <li key={f}>{f}</li>)}</ul></div>) : null}
        </div>
      ) : null}
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </article>
  );
}
