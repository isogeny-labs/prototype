import { Link } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { ComparisonTable, EmptyState, PageHeader, QueryBoundary } from "@/components";
import type { Recommendation } from "@/contracts";
import { fmtDateTime, humanize } from "@/lib/format";
import { actorName, byId, versionLabel } from "@/lib/lookup";

const TYPE: Record<Recommendation["type"], { label: string; cls: string; help: string }> = {
  supported_by_this_project: { label: "Supported by this project", cls: "border-ok/60 text-ok", help: "Backed by runs and checks in this project." },
  general_guidance: { label: "General guidance", cls: "border-info/60 text-info", help: "Standard practice; this project did not measure its effect." },
  hypothesis: { label: "Hypothesis", cls: "border-warn/60 text-warn", help: "Untested idea; needs an experiment before acting." },
};

export function ChangesPage() {
  const { project } = useProject();
  const q = useQuery(async () => {
    const [recs, changes, comparisons, runs, artifacts, approvals] = await Promise.all([services.evidenceLab.listRecommendations(project.id), services.evidenceLab.listExternalChanges(project.id), services.evidenceLab.listComparisons(project.id), services.evidenceLab.listRuns(project.id), services.evidenceLab.listArtifacts(project.id), services.approvals.list(project.id)]);
    return { recs, changes, comparisons, runs, artifacts, approvals };
  }, [project.id]);
  return (
    <>
      <PageHeader title="Changes" subtitle="Recommendations say what kind of claim they are. The customer makes the change outside the lab and reports it; retests compare before and after." />
      <QueryBoundary q={q} label="Loading changes">{({ recs, changes, comparisons, runs, artifacts, approvals }) => (
        <div className="space-y-6">
          <section>
            <h2 className="h3 mb-2">Recommendations</h2>
            {recs.length === 0 ? <EmptyState title="No recommendations" /> : <div className="grid gap-3">{recs.map((r) => { const t = TYPE[r.type]; const apr = r.approvalId ? approvals.find((a) => a.id === r.approvalId) : null; return (
              <article key={r.id} className="panel text-sm" data-testid="recommendation" data-type={r.type}>
                <div className="flex flex-wrap items-center gap-2"><span className={`tag ${t.cls}`} title={t.help}>{t.label}</span><span className="tag">{humanize(r.status)}</span>{apr ? <span className="text-xs text-muted">approval: {apr.decision}{apr.reviewerId ? ` by ${actorName(project, apr.reviewerId)}` : ""}</span> : null}<span className="ml-auto text-xs text-faint">{fmtDateTime(r.createdAt)}</span></div>
                <h3 className="mt-2 font-semibold">{r.title}</h3>
                {r.findingId ? <div className="text-xs"><Link to={`/p/${project.id}/findings/${r.findingId}`}>Linked finding</Link></div> : null}
                <dl className="kv mt-2">
                  <dt>Observed issue</dt><dd>{r.observedIssue}</dd>
                  <dt>Supporting evidence</dt><dd>{r.supportingEvidence.length ? r.supportingEvidence.map((e) => <span key={`${e.kind}-${e.id}`} className="tag mr-1">{e.label}</span>) : <span className="text-faint">none in this project</span>}</dd>
                  <dt>Proposed change</dt><dd>{r.proposedChange}</dd>
                  <dt>Guidance reference</dt><dd className="text-muted">{r.guidanceReference.join(" ")}</dd>
                  <dt>Expected benefit</dt><dd>{r.expectedBenefit}</dd>
                  <dt>Trade-offs</dt><dd><ul className="list-disc pl-4">{r.tradeOffs.map((x) => <li key={x}>{x}</li>)}</ul></dd>
                  <dt>Applicability limits</dt><dd className="text-muted"><ul className="list-disc pl-4">{r.applicabilityLimits.map((x) => <li key={x}>{x}</li>)}</ul></dd>
                  <dt>How to verify</dt><dd><ol className="list-decimal pl-4">{r.verificationSteps.map((x) => <li key={x}>{x}</li>)}</ol></dd>
                </dl>
              </article>
            ); })}</div>}
          </section>
          <section>
            <h2 className="h3 mb-2">External changes reported</h2>
            {changes.length === 0 ? <EmptyState title="No external changes reported" hint="When the customer ships a change, they report it here with the new artifact version; the lab never applies changes itself." /> : (
              <table className="tbl"><thead><tr><th>When</th><th>Reported by</th><th>Change</th><th>New artifact version</th><th>Links</th></tr></thead>
                <tbody>{changes.map((c) => <tr key={c.id} data-testid="external-change"><td className="text-xs">{fmtDateTime(c.reportedAt)}</td><td>{actorName(project, c.reportedBy)}</td><td>{c.description}</td><td>{versionLabel(artifacts, c.newArtifactVersionId)}</td><td className="text-xs">{c.findingId ? <Link to={`/p/${project.id}/findings/${c.findingId}`}>finding</Link> : null}{c.recommendationId ? <> · recommendation {c.recommendationId}</> : null}</td></tr>)}</tbody></table>
            )}
          </section>
          <section>
            <h2 className="h3 mb-2">Before / after comparisons</h2>
            {comparisons.length === 0 ? <EmptyState title="No comparisons yet" hint="Comparisons appear once a retest exists for a baseline run." /> : <div className="grid gap-4">{comparisons.map((c) => <ComparisonTable key={c.id} comparison={c} runsById={byId(runs)} projectId={project.id} />)}</div>}
          </section>
        </div>
      )}</QueryBoundary>
    </>
  );
}
