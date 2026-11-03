import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, EvidenceLabel, ExecutionModeBadge, IntegrityBadge, Marker, PageHeader, ProvenanceBadge, QueryBoundary, RunStatus } from "@/components";
import { fmtBytes, fmtDateTime, fmtValue, shortSha } from "@/lib/format";
import { actorName, runEvidenceLabel, testName, versionLabel } from "@/lib/lookup";

export function RunDetailPage() {
  const { project, template } = useProject();
  const { runId = "" } = useParams();
  const user = useAppStore((s) => s.user);
  const [msg, setMsg] = useState<string | null>(null);
  const q = useQuery(async () => {
    const run = await services.evidenceLab.getRun(project.id, runId);
    const [runs, tests, artifacts, checks, evidence, criteria, approvals] = await Promise.all([
      services.evidenceLab.listRuns(project.id), services.evidenceLab.listTests(project.id), services.evidenceLab.listArtifacts(project.id),
      services.evidenceLab.listChecks(project.id), services.evidenceLab.listEvidence(project.id), services.evidenceLab.listCriteria(project.id), services.approvals.list(project.id),
    ]);
    return { run, runs, tests, artifacts, checks, evidence, criteria, approvals };
  }, [project.id, runId]);

  async function retry(id: string) {
    setMsg(null);
    try { const r = await services.evidenceLab.retryRun(project.id, id, user.id); setMsg(`Queued run #${r.sequence} as a new record that supersedes this one (simulated).`); }
    catch (e) { setMsg(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
  }

  return (
    <QueryBoundary q={q} label="Loading run">{({ run, runs, tests, artifacts, checks, evidence, criteria, approvals }) => {
      const supersededBy = runs.find((r) => r.supersedesRunId === run.id);
      const prev = run.supersedesRunId ? runs.find((r) => r.id === run.supersedesRunId) : null;
      const ev = run.evidenceRecordId ? evidence.find((e) => e.id === run.evidenceRecordId) : null;
      const crit = criteria.find((c) => c.version === run.criteriaVersion);
      const approval = run.approvalId ? approvals.find((a) => a.id === run.approvalId) : null;
      const runChecks = checks.filter((c) => c.runId === run.id);
      return (
        <>
          <PageHeader title={`Run #${run.sequence}: ${testName(tests, run.testDefinitionId)}`} subtitle={<span className="flex flex-wrap items-center gap-2"><RunStatus run={run} superseded={Boolean(supersededBy)} /><ExecutionModeBadge mode={run.executionMode} /><ProvenanceBadge provenance={run.provenance} />{(() => { const l = runEvidenceLabel(run, checks); return l ? <EvidenceLabel label={l} /> : null; })()}{run.provenance === "illustrative" ? <Marker kind="sample" /> : null}</span>}
            actions={<>
              <Link className="btn-ghost btn-sm" to={`/p/${project.id}/runs`}>All runs</Link>
              {run.status === "failed" && !supersededBy ? <button type="button" className="btn btn-sm" onClick={() => retry(run.id)}>Retry as new run</button> : null}
            </>} />
          {msg ? <div className="callout-info mb-3" role="status">{msg}</div> : null}
          {supersededBy ? <div className="callout mb-3"><strong>Superseded by <Link to={`/p/${project.id}/runs/${supersededBy.id}`}>run #{supersededBy.sequence}</Link>.</strong> {supersededBy.correctionNote}</div> : null}
          {prev ? <div className="callout-info mb-3"><strong>Corrects <Link to={`/p/${project.id}/runs/${prev.id}`}>run #{prev.sequence}</Link>.</strong> {run.correctionNote}</div> : null}
          {run.failures.length > 0 ? <div className="callout-bad mb-3"><strong>Failures</strong><ul className="list-disc pl-4">{run.failures.map((f) => <li key={f}>{f}</li>)}</ul></div> : null}

          <div className="grid gap-4 xl:grid-cols-2">
            <section className="panel text-sm">
              <h2 className="h2 mb-2">Record</h2>
              <dl className="kv">
                <dt>Artifact version</dt><dd><Link to={`/p/${project.id}/artifacts`}>{versionLabel(artifacts, run.artifactVersionId)}</Link></dd>
                <dt>Test definition</dt><dd>{testName(tests, run.testDefinitionId)} <span className="text-faint">v{tests.find((t) => t.id === run.testDefinitionId)?.version ?? "?"}</span></dd>
                <dt>Criteria version</dt><dd>v{run.criteriaVersion}</dd>
                <dt>Requested by</dt><dd>{actorName(project, run.requestedBy)}</dd>
                <dt>Execution approval</dt><dd>{approval ? <Link to={`/p/${project.id}/approvals`}>{approval.decision} by {approval.reviewerId ? actorName(project, approval.reviewerId) : "—"}</Link> : <span className="text-faint">not required by the template for this test</span>}</dd>
                <dt>Created / started / finished</dt><dd className="text-xs">{fmtDateTime(run.createdAt)} / {fmtDateTime(run.startedAt)} / {fmtDateTime(run.finishedAt)}</dd>
                <dt>Repeat count</dt><dd>{run.repeatCount}</dd>
                <dt>Environment</dt><dd>{Object.entries(run.environment).map(([k, v]) => <div key={k}><span className="text-muted">{k}:</span> {v}</div>)}</dd>
                <dt>Tool versions</dt><dd>{Object.entries(run.toolVersions).map(([k, v]) => <div key={k}><span className="text-muted">{k}:</span> {v}</div>)}</dd>
                <dt>Commands</dt><dd>{run.commands.length ? run.commands.map((c) => <code key={c} className="block text-xs">{c}</code>) : <span className="text-faint">none recorded ({run.executionMode})</span>}</dd>
                <dt>Parameters</dt><dd>{Object.keys(run.parameters).length ? Object.entries(run.parameters).map(([k, v]) => <div key={k}><span className="text-muted">{k}:</span> {String(v)}</div>) : <span className="text-faint">none</span>}</dd>
                <dt>Seeds</dt><dd>{Object.keys(run.seeds).length ? Object.entries(run.seeds).map(([k, v]) => <div key={k}><span className="text-muted">{k}:</span> {String(v)}</div>) : <span className="text-faint">none</span>}</dd>
              </dl>
            </section>

            <section className="panel text-sm">
              <h2 className="h2 mb-2">Evidence record</h2>
              {ev ? (
                <dl className="kv">
                  <dt>Integrity</dt><dd><IntegrityBadge level={ev.integrity} /></dd>
                  <dt>Manifest SHA-256</dt><dd><code className="text-xs" title={ev.manifestSha256}>{shortSha(ev.manifestSha256, 32)}</code></dd>
                  <dt>Members</dt><dd>{ev.artifactRefs.map((a) => <div key={a.name} className="text-xs"><code>{a.name}</code> · {fmtBytes(a.sizeBytes)} · <span title={a.sha256}>{shortSha(a.sha256)}</span></div>)}</dd>
                  <dt>Signer</dt><dd>{ev.signer ? `${ev.signer.name} (${ev.signer.keyId})` : <span className="text-muted">none: not signed</span>}</dd>
                  <dt>Verification</dt><dd>{ev.verification.result} {ev.verification.checker ? `by ${ev.verification.checker}` : ""} {ev.verification.verifiedAt ? `· ${fmtDateTime(ev.verification.verifiedAt)}` : ""}<div className="text-xs text-muted">{ev.verification.notes}</div></dd>
                </dl>
              ) : <EmptyState title="No evidence record" hint={run.status === "completed" ? "Completed runs normally carry one." : "Written when the run completes."} />}
              <h2 className="h2 mb-2 mt-4">Limitations</h2>
              {run.limitations.length ? <ul className="list-disc pl-4 text-muted">{run.limitations.map((l) => <li key={l}>{l}</li>)}</ul> : <div className="text-faint">None recorded.</div>}
            </section>

            <section className="panel text-sm xl:col-span-2">
              <h2 className="h2 mb-2">Metrics</h2>
              {run.metrics.length === 0 ? <EmptyState title="No metrics" hint={run.status === "failed" ? "The run failed before producing a measurement." : "Nothing recorded yet."} /> : (
                <table className="tbl"><thead><tr><th>Metric</th><th>Value</th><th>How it was measured</th></tr></thead>
                  <tbody>{run.metrics.map((m) => <tr key={m.key} data-testid="metric"><td className="font-mono text-xs">{m.key}</td><td className="font-mono">{fmtValue(m.value, m.unit)}{run.provenance === "illustrative" ? <Marker kind="illustrative" className="ml-2" /> : null}</td><td className="text-muted">{m.definition}</td></tr>)}</tbody></table>
              )}
              {run.criteriaResults.length > 0 ? (<>
                <h2 className="h2 mb-2 mt-4">Against acceptance criteria v{run.criteriaVersion}</h2>
                <table className="tbl"><thead><tr><th>Criterion</th><th>Observed</th><th>Result</th></tr></thead>
                  <tbody>{run.criteriaResults.map((c) => { const item = crit?.items.find((i) => i.id === c.criteriaItemId); return <tr key={c.criteriaItemId}><td>{item?.text ?? c.criteriaItemId}{item?.metric ? <div className="font-mono text-xs text-faint">{item.metric} {item.operator} {item.threshold}{item.unit ? ` ${item.unit}` : ""}</div> : null}</td><td className="font-mono">{fmtValue(c.observed, item?.unit)}</td><td>{c.pass === true ? <span className="tag border-ok/60 text-ok">▲ Pass</span> : c.pass === false ? <span className="tag border-bad/60 text-bad">▼ Fail</span> : <span className="tag">—</span>}{c.note ? <div className="text-xs text-muted">{c.note}</div> : null}</td></tr>; })}</tbody></table>
              </>) : null}
            </section>

            <section className="panel text-sm xl:col-span-2">
              <h2 className="h2 mb-2">Cases</h2>
              {run.cases.length === 0 ? <div className="text-faint">No per-case table for this run.</div> : (
                <table className="tbl"><thead><tr><th>Case</th><th>Expected</th><th>Observed</th><th>Result</th></tr></thead>
                  <tbody>{run.cases.map((c) => <tr key={c.id} data-testid="case" data-pass={c.pass}><td><span className="font-mono text-xs">{c.id}</span> {c.name}{c.detail ? <div className="text-xs text-muted">{c.detail}</div> : null}</td><td>{c.expected}</td><td>{c.observed}</td><td>{c.pass ? <span className="tag border-ok/60 text-ok">▲ Pass</span> : <span className="tag border-bad/60 text-bad">▼ Fail</span>}</td></tr>)}</tbody></table>
              )}
            </section>

            <section className="panel text-sm">
              <h2 className="h2 mb-2">Log</h2>
              <pre className="max-h-72 overflow-auto rounded bg-bg p-3 text-xs">{run.logs.map((l) => `${l.t}  ${l.level.toUpperCase().padEnd(5)}  ${l.text}`).join("\n") || "(empty)"}</pre>
            </section>
            <section className="panel text-sm">
              <h2 className="h2 mb-2">Checks referencing this run</h2>
              {runChecks.length === 0 ? <div className="text-faint">None. {runEvidenceLabel(run, checks) ? `The label above (${runEvidenceLabel(run, checks)}) comes from the run itself: a completed deterministic run counts as a deterministic check, imported results as imported, simulated runs as an estimate.` : "No label until the run completes."}</div> : <ul className="list-disc pl-4">{runChecks.map((c) => <li key={c.id}>{c.method} {c.findingId ? <Link to={`/p/${project.id}/findings/${c.findingId}`}>(finding)</Link> : null}</li>)}</ul>}
              <div className="mt-4 text-xs text-faint">{template.disclaimers[0]}</div>
            </section>
          </div>
        </>
      );
    }}</QueryBoundary>
  );
}
