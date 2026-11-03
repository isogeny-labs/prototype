import type { Approval, Project } from "@/contracts";
import { actorName, isAgentId } from "@/lib/lookup";
import { fmtDateTime, humanize } from "@/lib/format";

const DECISION: Record<Approval["decision"], { label: string; glyph: string; cls: string }> = {
  pending: { label: "Pending", glyph: "◷", cls: "border-warn/60 text-warn" },
  approved: { label: "Approved", glyph: "✓", cls: "border-ok/60 text-ok" },
  rejected: { label: "Rejected", glyph: "✕", cls: "border-bad/60 text-bad" },
  changes_requested: { label: "Changes requested", glyph: "↺", cls: "border-info/60 text-info" },
};

/**
 * An approval is a record, never a boolean. Decision controls are passed in by the page (Phase 3);
 * the card itself only displays the record and why it exists.
 */
export function ApprovalCard({ approval, project, actions }: { approval: Approval; project: Project | null; actions?: React.ReactNode }) {
  const d = DECISION[approval.decision];
  return (
    <article className="panel text-sm" data-testid="approval-card" data-decision={approval.decision}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`tag ${d.cls}`}><span aria-hidden="true">{d.glyph}</span> {d.label}</span>
        <span className="tag">{humanize(approval.subjectType)}</span>
        <span className="ml-auto text-xs text-faint">requested {fmtDateTime(approval.requestedAt)}</span>
      </div>
      <h3 className="mt-2 font-semibold">{approval.subjectLabel}</h3>
      <dl className="kv mt-2">
        <dt>Requested by</dt><dd>{actorName(project, approval.requestedBy)}{isAgentId(approval.requestedBy) ? <span className="tag ml-2 border-sample/60 text-sample">Agent</span> : null}</dd>
        <dt>Why a human decides</dt><dd className="text-muted">{approval.rationale}</dd>
        {approval.decision !== "pending" ? (<>
          <dt>Decided by</dt><dd>{approval.reviewerId ? actorName(project, approval.reviewerId) : "—"} · {fmtDateTime(approval.decidedAt)}</dd>
          <dt>Note</dt><dd>{approval.note || <span className="text-faint">none</span>}</dd>
        </>) : null}
      </dl>
      {actions ? <div className="mt-3 flex flex-wrap items-center gap-2">{actions}</div> : null}
    </article>
  );
}
