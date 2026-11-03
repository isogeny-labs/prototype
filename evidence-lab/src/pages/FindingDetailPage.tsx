import { useState } from "react";
import { ServiceError } from "@/services";
import { useAppStore } from "@/store";
import { Link, useParams } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { CheckBadge, EmptyState, EvidenceLabel, FindingTimeline, Marker, PageHeader, QueryBoundary, RunStatus } from "@/components";
import { canResolve, computeEvidenceLabel, toUserFacingStatus } from "@/contracts";
import { humanize } from "@/lib/format";
import { byId, versionLabel } from "@/lib/lookup";

export function FindingDetailPage() {
  const { project, template } = useProject();
  const { fid = "" } = useParams();
  const [tech, setTech] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const user = useAppStore((s) => s.user);
  async function requestResolution(findingId: string, label: string) {
    setMsg(null);
    try { await services.approvals.request(project.id, { projectId: project.id, subjectType: "finding_resolution", subjectId: findingId, subjectLabel: label, requestedBy: user.id, rationale: "A finding is resolved only with a linked passing retest and a reviewer decision." }); setMsg("Resolution requested. A reviewer decides on the Approvals page; you cannot decide your own request."); }
    catch (e) { setMsg(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
  }
  async function investigate(findingId: string, artifactVersionId: string, summary: string) {
    setMsg(null);
    try { const p = await services.autoresearcher.create(project.id, { findingId, affectedArtifactVersionId: artifactVersionId, prompt: summary }); setMsg(`Investigation proposal "${p.title}" created (simulated) and sent for approval. No majority vote: a protocol decides.`); }
    catch (e) { setMsg(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
  }
  const q = useQuery(async () => {
    const { finding, checks } = await services.evidenceLab.getFinding(project.id, fid);
    const [runs, artifacts, recs, approvals, proposals] = await Promise.all([services.evidenceLab.listRuns(project.id), services.evidenceLab.listArtifacts(project.id), services.evidenceLab.listRecommendations(project.id), services.approvals.list(project.id), services.autoresearcher.list(project.id)]);
    return { finding, checks, runs, artifacts, recs, approvals, proposals };
  }, [project.id, fid]);

  return (
    <QueryBoundary q={q} label="Loading finding">{({ finding: f, checks, runs, artifacts, recs, approvals, proposals }) => {
      const runsById = byId(runs);
      const label = computeEvidenceLabel(checks, { hasImportedEvidence: f.evidenceRunIds.some((id) => runsById[id]?.provenance === "imported") });
      const status = toUserFacingStatus(f, runsById);
      const resolvable = canResolve(f, runsById);
      const rec = f.recommendationId ? recs.find((r) => r.id === f.recommendationId) : null;
      const pendingResolution = approvals.find((a) => a.subjectType === "finding_resolution" && a.subjectId === f.id && a.decision === "pending");
      const kinds = new Set(checks.map((c) => c.kind));
      const labelWhy = label === "Expert-reviewed" ? "a named human reviewer recorded a decision" : label === "Machine-checked" ? "a deterministic check or reproduced run supports it" : label === "Model-reviewed" ? "only a model judgment supports it" : label === "Imported" ? "the evidence was imported" : "only agent claims exist; agreement between agents does not raise the label";
      return (
        <>
          <PageHeader title="Finding" subtitle={<span className="flex flex-wrap items-center gap-2"><EvidenceLabel label={label} size="md" /><span className="tag">{status}</span><span className="tag">{humanize(f.origin)}</span>{f.isSeeded ? <Marker kind="sample" /> : null}</span>} actions={<Link className="btn-ghost btn-sm" to={`/p/${project.id}/findings`}>All findings</Link>} />
          <p className="mb-4 max-w-4xl text-base" data-testid="finding-statement">{f.statement}</p>
          {msg ? <div className="callout-info mb-3" role="status">{msg}</div> : null}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <div className="space-y-4">
              <section className="panel text-sm">
                <h2 className="h2 mb-1">Checks ({checks.length})</h2>
                <div className="mb-3 text-xs text-muted">Label is <strong>{label}</strong> because {labelWhy}. Kinds present: {[...kinds].map(humanize).join(", ") || "none"}.</div>
                {checks.length === 0 ? <EmptyState title="No checks recorded" /> : <div className="grid gap-2">{checks.map((c) => <CheckBadge key={c.id} check={c} />)}</div>}
              </section>
              {f.conflicts.length > 0 ? (
                <section className="panel text-sm" data-testid="conflicts">
                  <h2 className="h2 mb-2">Disagreements</h2>
                  {f.conflicts.map((c) => { const prop = c.investigationProposalId ? proposals.find((p) => p.id === c.investigationProposalId) : null; return (
                    <div key={c.id} className={`${c.resolved ? "callout-ok" : "callout"} mb-2`}>
                      <div className="font-semibold">{c.resolved ? "Resolved" : "Unresolved"}: {c.summary}</div>
                      <ul className="mt-1 list-disc pl-4">{c.between.map((b, i) => <li key={i}><span className="text-muted">{b.owner}:</span> {b.claim}</li>)}</ul>
                      {prop ? <div className="mt-1 text-xs">Investigation proposed: <Link to={`/p/${project.id}/research`}>{prop.title}</Link> (protocol v{prop.protocolVersion}, {humanize(prop.status).toLowerCase()})</div>
                        : !c.resolved ? <button type="button" className="btn-ghost btn-sm mt-2" onClick={() => investigate(f.id, f.artifactVersionIds[0] ?? "", c.summary)} data-testid="investigate">Investigate: propose an experiment</button> : null}
                    </div>
                  ); })}
                </section>
              ) : null}
              <section className="panel text-sm">
                <h2 className="h2 mb-2">Assumptions and limitations</h2>
                <div className="grid gap-3 md:grid-cols-2">
                  <div><div className="h3">Assumptions</div>{f.assumptions.length ? <ul className="list-disc pl-4">{f.assumptions.map((a) => <li key={a}>{a}</li>)}</ul> : <div className="text-faint">None stated.</div>}</div>
                  <div><div className="h3">Limitations</div>{f.limitations.length ? <ul className="list-disc pl-4 text-muted">{f.limitations.map((a) => <li key={a}>{a}</li>)}</ul> : <div className="text-faint">None stated.</div>}</div>
                </div>
              </section>
              <section className="panel text-sm">
                <button type="button" className="btn-ghost btn-sm" aria-expanded={tech} onClick={() => setTech((t) => !t)}>{tech ? "Hide" : "Show"} technical detail</button>
                {tech ? <p className="mt-3 whitespace-pre-wrap text-muted" data-testid="technical-detail">{f.technicalDetail}</p> : null}
              </section>
            </div>
            <div className="space-y-4">
              <section className="panel text-sm">
                <h2 className="h2 mb-2">Timeline</h2>
                <FindingTimeline history={f.statusHistory} />
                <div className="mt-3 text-xs text-faint">Backend status: {f.status} → shown as "{status}".</div>
              </section>
              <section className="panel text-sm">
                <h2 className="h2 mb-2">Evidence</h2>
                <dl className="kv">
                  <dt>Artifact versions</dt><dd>{f.artifactVersionIds.map((id) => <div key={id}><Link to={`/p/${project.id}/artifacts`}>{versionLabel(artifacts, id)}</Link></div>)}</dd>
                  <dt>Evidence runs</dt><dd>{f.evidenceRunIds.length ? f.evidenceRunIds.map((id) => { const r = runsById[id]; return r ? <div key={id} className="flex items-center gap-2"><Link to={`/p/${project.id}/runs/${id}`}>Run #{r.sequence}</Link><RunStatus run={r} /></div> : <div key={id}>{id}</div>; }) : <span className="text-faint">none</span>}</dd>
                  <dt>Retest runs</dt><dd>{f.retestRunIds.length ? f.retestRunIds.map((id) => { const r = runsById[id]; return r ? <div key={id} className="flex items-center gap-2"><Link to={`/p/${project.id}/runs/${id}`}>Run #{r.sequence}</Link><RunStatus run={r} /></div> : <div key={id}>{id}</div>; }) : <span className="text-faint">none yet</span>}</dd>
                  <dt>Revised artifact</dt><dd>{f.revisedArtifactVersionId ? versionLabel(artifacts, f.revisedArtifactVersionId) : <span className="text-faint">no external change reported</span>}</dd>
                </dl>
              </section>
              <section className="panel text-sm">
                <h2 className="h2 mb-2">Recommendation and resolution</h2>
                {rec ? <div><Link to={`/p/${project.id}/changes`}>{rec.title}</Link><div className="text-xs text-muted">{humanize(rec.type)} · {humanize(rec.status)}</div></div> : <div className="text-faint">No recommendation linked.</div>}
                <div className={`mt-3 ${resolvable.ok ? "callout-ok" : "callout"}`}>
                  <div className="font-semibold">{resolvable.ok ? "Eligible for resolution within tested scope" : "Not eligible for resolution"}</div>
                  <div className="text-muted">{resolvable.reason}</div>
                  {pendingResolution ? <div className="mt-1 text-xs">Resolution request pending: <Link to={`/p/${project.id}/approvals`}>decide on the Approvals page</Link>.</div> : null}
                  {resolvable.ok && !pendingResolution && f.status !== "closed" ? <button type="button" className="btn btn-sm mt-2" onClick={() => requestResolution(f.id, `Resolve finding ${f.id} within tested scope`)} data-testid="request-resolution">Request resolution</button> : null}
                  {f.status === "closed" ? <div className="mt-1 text-xs">Closed. Resolution is scoped to the retests listed; nothing beyond them is claimed.</div> : null}
                </div>
              </section>
              <div className="text-xs text-faint">{template.disclaimers[0]}</div>
            </div>
          </div>
        </>
      );
    }}</QueryBoundary>
  );
}
