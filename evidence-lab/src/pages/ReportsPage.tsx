import { useState } from "react";
import { Link } from "react-router-dom";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, EvidenceLabel, IntegrityBadge, Marker, PageHeader, QueryBoundary } from "@/components";
import { computeEvidenceLabel, toUserFacingStatus } from "@/contracts";
import { fmtDate, fmtDateTime, fmtValue, humanize, shortSha } from "@/lib/format";
import { byId, latestTargetVersion, supersededIds, testName, versionLabel } from "@/lib/lookup";

type Tab = "handoff" | "bundle";

export function ReportsPage() {
  const { project, template } = useProject();
  const [tab, setTab] = useState<Tab>("handoff");
  const q = useQuery(async () => {
    const [findings, checks, runs, evidence, criteria, artifacts, tests, recs, changes, comparisons, approvals] = await Promise.all([
      services.evidenceLab.listFindings(project.id), services.evidenceLab.listChecks(project.id), services.evidenceLab.listRuns(project.id), services.evidenceLab.listEvidence(project.id),
      services.evidenceLab.listCriteria(project.id), services.evidenceLab.listArtifacts(project.id), services.evidenceLab.listTests(project.id), services.evidenceLab.listRecommendations(project.id),
      services.evidenceLab.listExternalChanges(project.id), services.evidenceLab.listComparisons(project.id), services.approvals.list(project.id),
    ]);
    return { findings, checks, runs, evidence, criteria, artifacts, tests, recs, changes, comparisons, approvals };
  }, [project.id]);
  const [exp, setExp] = useState<{ kind: "ok" | "bad"; text: string } | null>(null);
  async function doExport(kind: Tab) {
    setExp({ kind: "ok", text: "Preparing…" });
    try {
      if (kind === "handoff") { const r = await services.evidenceLab.exportHandoff(project.id); setExp({ kind: "ok", text: `Simulated export: ${r.format} · ${r.sizeBytes.toLocaleString()} bytes · sha256 ${shortSha(r.sha256, 16)} · generated ${fmtDateTime(r.generatedAt)}. ${r.note}` }); }
      else { const r = await services.evidenceLab.exportEvidenceBundle(project.id); setExp({ kind: "ok", text: `Simulated export: ${r.format} · ${r.members} members · manifest ${shortSha(r.manifestSha256, 16)} · signed: ${r.signed ? "yes" : "no"} · generated ${fmtDateTime(r.generatedAt)}. ${r.note}` }); }
    } catch (e) { setExp({ kind: "bad", text: e instanceof ServiceError ? `${e.message} (${e.code})` : String(e) }); }
  }
  return (
    <>
      <PageHeader title="Reports" subtitle="What a reader receives: the engineering handoff (plain language, every claim labelled and bounded) and the evidence bundle (what was hashed, by whom, and how to verify it). Export is simulated: no file is produced." actions={
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" className="flex rounded-md border border-line text-xs">
            {(["handoff", "bundle"] as Tab[]).map((t) => <button key={t} role="tab" aria-selected={tab === t} type="button" className={`px-3 py-1.5 ${tab === t ? "bg-panel-2 text-ink" : "text-muted"}`} onClick={() => setTab(t)} data-testid={`tab-${t}`}>{t === "handoff" ? "Engineering handoff" : "Evidence bundle"}</button>)}
          </div>
          <button type="button" className="btn btn-sm" onClick={() => doExport(tab)} data-testid="export">Export (simulated)</button>
        </div>} />
      {exp ? <div className={`${exp.kind === "ok" ? "callout-info" : "callout-bad"} mb-3 text-xs`} role="status" data-testid="export-result">{exp.text}</div> : null}
      <QueryBoundary q={q} label="Loading report data">{(d) => tab === "handoff" ? <Handoff d={d} /> : <Bundle d={d} />}</QueryBoundary>
    </>
  );

  function Handoff({ d }: { d: NonNullable<typeof q.data> }) {
    const runsById = byId(d.runs); const sup = supersededIds(d.runs);
    const live = d.runs.filter((r) => r.status === "completed" && !sup.has(r.id));
    const crit = d.criteria.find((c) => c.version === project.currentCriteriaVersion);
    const target = latestTargetVersion(project.packId, d.artifacts);
    const openQuestions = project.intakeQuestions.filter((q) => q.status !== "answered");
    const untestedRunnable = d.tests.filter((t) => t.runnable && !live.some((r) => r.testDefinitionId === t.id && (!target || r.artifactVersionId === target.id)));
    const notRunnable = d.tests.filter((t) => !t.runnable);
    return (
      <article className="mx-auto max-w-4xl space-y-5 text-sm" data-testid="handoff-preview">
        <header className="panel">
          <div className="flex flex-wrap items-center gap-2"><span className="tag">Engineering handoff</span><Marker kind="sample" /><span className="ml-auto text-xs text-faint">preview generated {fmtDate(new Date().toISOString())}</span></div>
          <h2 className="h1 mt-2">{project.name}</h2>
          <div className="text-muted">{humanize(project.packId)} · {template.name} v{template.version} · acceptance criteria v{project.currentCriteriaVersion} · {d.runs.length} runs · {d.findings.length} findings</div>
          <p className="mt-3">{project.summary}</p>
        </header>
        <section className="panel">
          <h3 className="h2 mb-2">1. Scope, assumptions and open questions</h3>
          <div className="h3">Goal</div><p>{project.goal}</p>
          <div className="h3 mt-2">Constraints</div><ul className="list-disc pl-4">{project.constraints.map((c) => <li key={c}>{c}</li>)}</ul>
          <div className="h3 mt-2">Assumptions and open intake questions</div>
          {openQuestions.length === 0 ? <div className="text-muted">None.</div> : <ul className="list-disc pl-4">{openQuestions.map((q) => <li key={q.id}><span className="tag mr-1">{q.status}</span>{q.question}{q.assumption ? <span className="text-muted"> Assumed: {q.assumption}</span> : <span className="text-muted"> Unanswered.</span>}</li>)}</ul>}
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">2. What was tested</h3>
          <div className="h3">Artifact under test</div>
          <div>{target ? `${target.artifactName} ${target.version} (sha256 ${shortSha(target.sha256, 16)}, ${humanize(target.provenance)})` : "—"}</div>
          <div className="h3 mt-2">Tests with a completed, non-superseded run on it</div>
          <ul className="list-disc pl-4">{[...new Set(live.filter((r) => !target || r.artifactVersionId === target.id).map((r) => r.testDefinitionId))].map((id) => <li key={id}>{testName(d.tests, id)}</li>)}</ul>
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">3. Results against acceptance criteria v{crit?.version ?? "?"}</h3>
          <table className="tbl"><thead><tr><th>Criterion</th><th>Latest non-superseded result</th><th>From</th></tr></thead>
            <tbody>{(crit?.items ?? []).map((it) => { const r = live.filter((x) => x.criteriaResults.some((c) => c.criteriaItemId === it.id)).sort((a, b) => b.sequence - a.sequence)[0]; const res = r?.criteriaResults.find((c) => c.criteriaItemId === it.id); return <tr key={it.id}><td>{it.text}</td><td>{r && res ? <>{res.pass ? <span className="tag border-ok/60 text-ok">▲ Pass</span> : <span className="tag border-bad/60 text-bad">▼ Fail</span>} <span className="font-mono">{fmtValue(res.observed, it.unit)}</span> <Marker kind="illustrative" /></> : <span className="tag">Untested</span>}</td><td>{r ? <Link to={`/p/${project.id}/runs/${r.id}`}>Run #{r.sequence}</Link> : "—"}</td></tr>; })}</tbody></table>
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">4. Findings</h3>
          {d.findings.length === 0 ? <EmptyState title="No findings" /> : d.findings.map((f) => { const fc = d.checks.filter((c) => f.checkIds.includes(c.id)); return (
            <div key={f.id} className="mb-3 border-b border-line pb-3 last:mb-0 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2"><EvidenceLabel label={computeEvidenceLabel(fc, { hasImportedEvidence: f.evidenceRunIds.some((id) => runsById[id]?.provenance === "imported") })} /><span className="tag">{toUserFacingStatus(f, runsById)}</span><Link className="ml-auto text-xs" to={`/p/${project.id}/findings/${f.id}`}>{f.id}</Link></div>
              <p className="mt-1">{f.statement}</p>
              <div className="mt-1 text-xs text-muted">Checks: {fc.map((c) => humanize(c.kind).toLowerCase()).join(", ") || "none"}. Limitations: {f.limitations.join(" ") || "none stated."}</div>
            </div>
          ); })}
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">5. Recommendations, changes and retests</h3>
          {d.recs.length === 0 ? <div className="text-muted">No recommendations.</div> : <ul className="space-y-2">{d.recs.map((r) => <li key={r.id}><span className={`tag ${r.type === "supported_by_this_project" ? "border-ok/60 text-ok" : r.type === "hypothesis" ? "border-warn/60 text-warn" : "border-info/60 text-info"}`}>{humanize(r.type)}</span> <span className="tag">{humanize(r.status)}</span> <strong>{r.title}</strong><div className="text-xs text-muted">{r.proposedChange} Limits: {r.applicabilityLimits.join(" ")}</div></li>)}</ul>}
          {d.changes.length > 0 ? <ul className="mt-2 list-disc pl-4">{d.changes.map((c) => <li key={c.id}>{fmtDate(c.reportedAt)}: {c.description} → {versionLabel(d.artifacts, c.newArtifactVersionId)}</li>)}</ul> : null}
          {d.comparisons.map((c) => <div key={c.id} className="mt-2 text-xs"><strong>{c.title}:</strong> {c.metricDeltas.map((m) => `${m.key} ${fmtValue(m.baseline)} → ${fmtValue(m.candidate)}${m.regression ? " (regression)" : ""}`).join("; ")}. Previously failing now passing: {c.previouslyFailingCases.filter((x) => !x.baselinePass && x.candidatePass).map((x) => x.name).join(", ") || "none"}. {c.newRegressions.length ? `New regressions: ${c.newRegressions.join(", ")}.` : "No new regressions."}</div>)}
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">6. What this does not establish</h3>
          <ul className="list-disc pl-4">
            {notRunnable.map((t) => <li key={t.id}>{t.name}: not runnable here. {t.unsupportedReason}</li>)}
            {untestedRunnable.map((t) => <li key={t.id}>{t.name}: supported but not run on the latest artifact version.</li>)}
            {template.disclaimers.map((x) => <li key={x} className="text-muted">{x}</li>)}
          </ul>
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">7. Decisions on record</h3>
          <ul className="list-disc pl-4 text-xs">{d.approvals.filter((a) => a.decision !== "pending").map((a) => <li key={a.id}>{humanize(a.subjectType)}: {a.subjectLabel} — {a.decision.replace(/_/g, " ")} by {project.people.find((p) => p.id === a.reviewerId)?.name ?? a.reviewerId} on {fmtDate(a.decidedAt)}</li>)}</ul>
        </section>
      </article>
    );
  }

  function Bundle({ d }: { d: NonNullable<typeof q.data> }) {
    const runsById = byId(d.runs);
    const members = d.evidence.flatMap((e) => e.artifactRefs.map((a) => ({ ...a, record: e })));
    return (
      <article className="mx-auto max-w-4xl space-y-5 text-sm" data-testid="bundle-preview">
        <header className="panel">
          <div className="flex flex-wrap items-center gap-2"><span className="tag">Evidence bundle</span><IntegrityBadge level="hashed" /><Marker kind="sample" /></div>
          <h2 className="h1 mt-2">{project.name}: evidence-package/2 (preview)</h2>
          <div className="text-muted">{d.evidence.length} evidence records · {members.length} member files · manifest SHA-256 computed at export · <strong className="text-ink">not signed</strong> · Cairn verification not connected.</div>
        </header>
        <section className="panel">
          <h3 className="h2 mb-2">How to verify</h3>
          <ol className="list-decimal pl-4">
            <li>Recompute SHA-256 for every member file and compare with the manifest.</li>
            <li>Recompute the manifest hash and compare with the value printed on the handoff.</li>
            <li>Signature and Cairn checks: <span className="text-warn">not available</span>; the existing backend export is a hashed manifest with a verify step, and signing is integration pending.</li>
          </ol>
        </section>
        <section className="panel">
          <h3 className="h2 mb-2">Manifest</h3>
          <table className="tbl"><thead><tr><th>Record</th><th>Run</th><th>Integrity</th><th>Member</th><th>Size</th><th>SHA-256</th></tr></thead>
            <tbody>{members.map((m) => { const r = m.record.runId ? runsById[m.record.runId] : null; return <tr key={`${m.record.id}-${m.name}`}><td className="font-mono text-xs">{m.record.id}</td><td>{r ? <Link to={`/p/${project.id}/runs/${r.id}`}>#{r.sequence}</Link> : "—"}</td><td><IntegrityBadge level={m.record.integrity} /></td><td className="font-mono text-xs">{m.name}</td><td className="text-xs">{m.sizeBytes.toLocaleString()} B</td><td className="font-mono text-xs" title={m.sha256}>{shortSha(m.sha256, 20)}</td></tr>; })}</tbody></table>
          <div className="mt-2 text-xs text-faint">Verification status per record: {d.evidence.map((e) => `${e.id} ${e.verification.result}`).join(" · ")}.</div>
        </section>
      </article>
    );
  }
}
