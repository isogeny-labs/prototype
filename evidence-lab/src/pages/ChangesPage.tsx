import { useState } from "react";
import { Link } from "react-router-dom";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import { ComparisonTable, EmptyState, PageHeader, QueryBoundary } from "@/components";
import type { Artifact, Finding, Recommendation, Run, TestDefinition } from "@/contracts";
import { fmtDateTime, humanize } from "@/lib/format";
import { actorName, allVersions, byId, versionLabel } from "@/lib/lookup";

/** The customer makes the change outside the platform and reports it here with the new artifact version. */
function ReportChangeForm({ projectId, findings, artifacts, recs, onDone }: { projectId: string; findings: Finding[]; artifacts: Artifact[]; recs: Recommendation[]; onDone: (m: string) => void }) {
  const user = useAppStore((s) => s.user);
  const open = findings.filter((f) => !["closed", "not_relevant"].includes(f.status));
  const versions = allVersions(artifacts);
  const [findingId, setFindingId] = useState(open[0]?.id ?? "");
  const [versionId, setVersionId] = useState(versions.at(-1)?.id ?? "");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const f = findings.find((x) => x.id === findingId);
      await services.evidenceLab.reportExternalChange(projectId, { projectId, recommendationId: f?.recommendationId ?? null, findingId: findingId || null, reportedBy: user.id, description: desc, newArtifactVersionId: versionId });
      onDone("External change recorded. The finding now awaits a retest; request one below or from the Tests page."); setDesc("");
    } catch (x) { setErr(x instanceof ServiceError ? x.message : String(x)); } finally { setBusy(false); }
  }
  if (versions.length === 0) return null;
  return (
    <form className="panel text-sm" onSubmit={submit} data-testid="report-change-form">
      <div className="h2 mb-2">Report an external change</div>
      <div className="grid gap-2 md:grid-cols-3">
        <label className="text-xs text-muted">Finding addressed<select className="input mt-1" value={findingId} onChange={(e) => setFindingId(e.target.value)}><option value="">— none —</option>{open.map((f) => <option key={f.id} value={f.id}>{f.id}: {f.statement.slice(0, 60)}…</option>)}</select></label>
        <label className="text-xs text-muted">New artifact version<select className="input mt-1" value={versionId} onChange={(e) => setVersionId(e.target.value)}>{versions.map((v) => <option key={v.id} value={v.id}>{v.artifactName} {v.version}</option>)}</select></label>
        <label className="text-xs text-muted">What changed<input className="input mt-1" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="e.g. shipped 1.4.4 with …" required /></label>
      </div>
      <div className="mt-2 flex items-center gap-2"><button type="submit" className="btn btn-sm" disabled={busy || !desc.trim()} data-testid="report-change-submit">Report change</button><span className="text-xs text-faint">Reported by {user.name}. Nothing is changed by the lab itself; this records that the customer changed something ({recs.length} recommendation{recs.length === 1 ? "" : "s"} on file).</span></div>
      {err ? <div className="callout-bad mt-2 text-xs" role="alert">{err}</div> : null}
    </form>
  );
}

function RetestButton({ projectId, finding, runs, tests, onDone }: { projectId: string; finding: Finding; runs: Run[]; tests: TestDefinition[]; onDone: (m: string) => void }) {
  const user = useAppStore((s) => s.user);
  const [busy, setBusy] = useState(false);
  const failing = runs.filter((r) => finding.evidenceRunIds.includes(r.id)).sort((a, b) => b.sequence - a.sequence)[0];
  const test = failing ? tests.find((t) => t.id === failing.testDefinitionId) : undefined;
  if (!finding.revisedArtifactVersionId || !test?.runnable) return null;
  async function retest() {
    setBusy(true);
    try { const r = await services.evidenceLab.requestRun(projectId, { artifactVersionId: finding.revisedArtifactVersionId!, testDefinitionId: test!.id, requestedBy: user.id }); onDone(`Retest requested as run #${r.sequence} (${test!.name}); it awaits execution approval.`); }
    catch (e) { onDone(e instanceof ServiceError ? e.message : String(e)); } finally { setBusy(false); }
  }
  return <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={retest} data-testid="request-retest">Request retest: {test.name}</button>;
}

const TYPE: Record<Recommendation["type"], { label: string; cls: string; help: string }> = {
  supported_by_this_project: { label: "Supported by this project", cls: "border-ok/60 text-ok", help: "Backed by runs and checks in this project." },
  general_guidance: { label: "General guidance", cls: "border-info/60 text-info", help: "Standard practice; this project did not measure its effect." },
  hypothesis: { label: "Hypothesis", cls: "border-warn/60 text-warn", help: "Untested idea; needs an experiment before acting." },
};

export function ChangesPage() {
  const { project } = useProject();
  const q = useQuery(async () => {
    const [recs, changes, comparisons, runs, artifacts, approvals, findings, tests] = await Promise.all([services.evidenceLab.listRecommendations(project.id), services.evidenceLab.listExternalChanges(project.id), services.evidenceLab.listComparisons(project.id), services.evidenceLab.listRuns(project.id), services.evidenceLab.listArtifacts(project.id), services.approvals.list(project.id), services.evidenceLab.listFindings(project.id), services.evidenceLab.listTests(project.id)]);
    return { recs, changes, comparisons, runs, artifacts, approvals, findings, tests };
  }, [project.id]);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <>
      <PageHeader title="Changes" subtitle="Recommendations say what kind of claim they are. The customer makes the change outside the lab and reports it; retests compare before and after." />
      {msg ? <div className="callout-info mb-3 text-sm" role="status" data-testid="changes-message">{msg}</div> : null}
      <QueryBoundary q={q} label="Loading changes">{({ recs, changes, comparisons, runs, artifacts, approvals, findings, tests }) => (
        <div className="space-y-6">
          <ReportChangeForm projectId={project.id} findings={findings} artifacts={artifacts} recs={recs} onDone={setMsg} />
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
                <tbody>{changes.map((c) => { const f = c.findingId ? findings.find((x) => x.id === c.findingId) : undefined; return <tr key={c.id} data-testid="external-change"><td className="text-xs">{fmtDateTime(c.reportedAt)}</td><td>{actorName(project, c.reportedBy)}</td><td>{c.description}</td><td>{versionLabel(artifacts, c.newArtifactVersionId)}</td><td className="text-xs">{c.findingId ? <Link to={`/p/${project.id}/findings/${c.findingId}`}>finding</Link> : null}{c.recommendationId ? <> · recommendation {c.recommendationId}</> : null}{f ? <div className="mt-1"><RetestButton projectId={project.id} finding={f} runs={runs} tests={tests} onDone={setMsg} /></div> : null}</td></tr>; })}</tbody></table>
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
