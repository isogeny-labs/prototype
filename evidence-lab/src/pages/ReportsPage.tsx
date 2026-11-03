import { useState } from "react";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { EvidenceLabel, IntegrityBadge, Marker, PageHeader, QueryBoundary } from "@/components";
import { computeEvidenceLabel, toUserFacingStatus } from "@/contracts";
import { fmtDateTime, shortSha } from "@/lib/format";
import { byId, supersededIds } from "@/lib/lookup";

export function ReportsPage() {
  const { project, template } = useProject();
  const q = useQuery(async () => {
    const [findings, checks, runs, evidence, criteria] = await Promise.all([services.evidenceLab.listFindings(project.id), services.evidenceLab.listChecks(project.id), services.evidenceLab.listRuns(project.id), services.evidenceLab.listEvidence(project.id), services.evidenceLab.listCriteria(project.id)]);
    return { findings, checks, runs, evidence, criteria };
  }, [project.id]);
  const [exp, setExp] = useState<string | null>(null);
  async function doExport(kind: "handoff" | "bundle") {
    setExp("Preparing…");
    try {
      if (kind === "handoff") { const r = await services.evidenceLab.exportHandoff(project.id); setExp(`${r.format} · ${r.sizeBytes} bytes · sha256 ${shortSha(r.sha256, 16)} · ${r.note}`); }
      else { const r = await services.evidenceLab.exportEvidenceBundle(project.id); setExp(`${r.format} · ${r.members} members · manifest ${shortSha(r.manifestSha256, 16)} · signed: ${r.signed ? "yes" : "no"} · ${r.note}`); }
    } catch (e) { setExp(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
  }
  return (
    <>
      <PageHeader title="Reports" subtitle="Report preview: what a reader gets, in plain language, with every claim's label and limits. Full preview, handoff export and compliance export arrive in Phase 3." actions={<><button type="button" className="btn-ghost btn-sm" onClick={() => doExport("handoff")}>Preview handoff export</button><button type="button" className="btn-ghost btn-sm" onClick={() => doExport("bundle")}>Preview evidence bundle</button></>} />
      {exp ? <div className="callout-info mb-3 text-xs" role="status">{exp}</div> : null}
      <QueryBoundary q={q} label="Loading report data">{({ findings, checks, runs, evidence, criteria }) => {
        const runsById = byId(runs); const sup = supersededIds(runs); const crit = criteria.find((c) => c.version === project.currentCriteriaVersion);
        const live = runs.filter((r) => r.status === "completed" && !sup.has(r.id));
        return (
          <div className="grid gap-4 xl:grid-cols-2">
            <section className="panel text-sm xl:col-span-2">
              <div className="flex items-center gap-2"><h2 className="h2">Summary</h2><Marker kind="sample" /></div>
              <p className="mt-2">{project.summary}</p>
              <ul className="mt-3 list-disc pl-4 text-muted">{template.disclaimers.map((d) => <li key={d}>{d}</li>)}</ul>
            </section>
            <section className="panel text-sm">
              <h2 className="h2 mb-2">Findings and their labels</h2>
              <table className="tbl"><thead><tr><th>Finding</th><th>Label</th><th>Status</th></tr></thead>
                <tbody>{findings.map((f) => <tr key={f.id}><td>{f.statement}</td><td><EvidenceLabel label={computeEvidenceLabel(checks.filter((c) => f.checkIds.includes(c.id)), { hasImportedEvidence: f.evidenceRunIds.some((id) => runsById[id]?.provenance === "imported") })} /></td><td><span className="tag">{toUserFacingStatus(f, runsById)}</span></td></tr>)}</tbody></table>
            </section>
            <section className="panel text-sm">
              <h2 className="h2 mb-2">Acceptance criteria coverage (v{crit?.version ?? "?"})</h2>
              <table className="tbl"><thead><tr><th>Criterion</th><th>Latest non-superseded result</th></tr></thead>
                <tbody>{(crit?.items ?? []).map((it) => { const r = live.filter((x) => x.criteriaResults.some((c) => c.criteriaItemId === it.id)).sort((a, b) => b.sequence - a.sequence)[0]; const res = r?.criteriaResults.find((c) => c.criteriaItemId === it.id); return <tr key={it.id}><td>{it.text}</td><td>{r && res ? <>{res.pass ? <span className="tag border-ok/60 text-ok">▲ Pass</span> : <span className="tag border-bad/60 text-bad">▼ Fail</span>} <span className="text-xs text-muted">run #{r.sequence}</span></> : <span className="tag">Untested</span>}</td></tr>; })}</tbody></table>
            </section>
            <section className="panel text-sm xl:col-span-2">
              <h2 className="h2 mb-2">Evidence records</h2>
              <table className="tbl"><thead><tr><th>Record</th><th>Run</th><th>Integrity</th><th>Manifest</th><th>Verification</th></tr></thead>
                <tbody>{evidence.map((e) => { const r = e.runId ? runsById[e.runId] : null; return <tr key={e.id}><td className="font-mono text-xs">{e.id}</td><td>{r ? `#${r.sequence}` : "—"}</td><td><IntegrityBadge level={e.integrity} /></td><td className="font-mono text-xs" title={e.manifestSha256}>{shortSha(e.manifestSha256, 16)}</td><td className="text-xs">{e.verification.result}{e.verification.verifiedAt ? ` · ${fmtDateTime(e.verification.verifiedAt)}` : ""}</td></tr>; })}</tbody></table>
              <div className="mt-2 text-xs text-faint">No record here is signed or Cairn-verified: the mock never upgrades integrity, and nothing is marked cairn_verified in the sample data.</div>
            </section>
          </div>
        );
      }}</QueryBoundary>
    </>
  );
}
