import { useState } from "react";
import { Link } from "react-router-dom";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, PageHeader, QueryBoundary } from "@/components";
import { humanize } from "@/lib/format";
import { latestTargetVersion } from "@/lib/lookup";

const NO_TESTS: string[] = [];
const KIND_CLS = { supported: "border-ok/60 text-ok", proposed: "border-info/60 text-info", imported: "border-ivory/60 text-ivory" } as const;

export function TestsPage() {
  const { project, template } = useProject();
  const user = useAppStore((s) => s.user);
  const chosenRaw = useAppStore((s) => s.viewConfig[project.id]?.chosenTestIds);
  const chosen = chosenRaw ?? NO_TESTS;
  const q = useQuery(async () => ({ tests: await services.evidenceLab.listTests(project.id), runs: await services.evidenceLab.listRuns(project.id), artifacts: await services.evidenceLab.listArtifacts(project.id) }), [project.id]);
  const [msg, setMsg] = useState<{ kind: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function request(testId: string, artifactVersionId: string) {
    setBusy(testId); setMsg(null);
    try {
      const run = await services.evidenceLab.requestRun(project.id, { artifactVersionId, testDefinitionId: testId, requestedBy: user.id });
      setMsg({ kind: "ok", text: `Run #${run.sequence} requested (simulated). It awaits execution approval on the Approvals page.` });
    } catch (e) { setMsg({ kind: "bad", text: e instanceof ServiceError ? `${e.message} (${e.code})` : String(e) }); }
    finally { setBusy(null); }
  }

  return (
    <>
      <PageHeader title="Tests" subtitle="Test definitions are versioned records. Unsupported and imported tests are never shown as runnable; their path (import results or adapter) is stated instead." />
      {msg ? <div className={`${msg.kind === "ok" ? "callout-ok" : "callout-bad"} mb-3`} role="status" data-testid="tests-message">{msg.text}</div> : null}
      <QueryBoundary q={q} label="Loading tests">{({ tests, runs, artifacts }) => {
        const latest = latestTargetVersion(project.packId, artifacts);
        if (tests.length === 0) return <EmptyState title="No test definitions for this pack" />;
        const shownTests = chosen.length ? tests.filter((t) => chosen.includes(t.id)) : tests;
        return (<>
          {chosen.length ? <div className="callout-info mb-2 text-xs" data-testid="view-filter-note">View filtered by the assistant: {shownTests.length} of {tests.length} tests shown. Ask it to "reset the view" to show all.</div> : null}
          <table className="tbl" data-testid="tests-table">
            <thead><tr><th>Test</th><th>Kind</th><th>Acceptance rule</th><th>Runner</th><th>Runs</th><th>Action</th></tr></thead>
            <tbody>
              {shownTests.map((t) => { const n = runs.filter((r) => r.testDefinitionId === t.id).length; const inTemplate = template.supportedTestDefinitionIds.includes(t.id); return (
                <tr key={t.id} data-testid="test-row" data-runnable={t.runnable}>
                  <td><div className="font-medium">{t.name} <span className="text-xs text-faint">v{t.version}</span></div><div className="text-xs text-muted">{t.description}</div>{t.vectorSource ? <div className="text-xs text-faint">Vectors: {t.vectorSource}</div> : null}</td>
                  <td><span className={`tag ${KIND_CLS[t.kind]}`}>{humanize(t.kind)}</span>{!inTemplate && t.runnable ? <div className="mt-1 text-xs text-faint">not in template</div> : null}</td>
                  <td className="text-xs">{t.acceptanceRule.description}{t.acceptanceRule.metric ? <div className="font-mono text-faint">{t.acceptanceRule.metric} {t.acceptanceRule.operator} {t.acceptanceRule.threshold}{t.acceptanceRule.unit ? ` ${t.acceptanceRule.unit}` : ""}</div> : null}</td>
                  <td className="text-xs">{t.runner}<div className="text-faint">{t.runnerVersion} · {t.resourceLimits.timeoutSeconds ? `${t.resourceLimits.timeoutSeconds}s, ${t.resourceLimits.memoryMb} MB, network ${t.resourceLimits.network}` : "n/a"}</div></td>
                  <td>{n > 0 ? <Link to={`/p/${project.id}/runs`}>{n}</Link> : <span className="text-faint">0</span>}</td>
                  <td>
                    {t.runnable && latest ? <button type="button" className="btn btn-sm" disabled={busy === t.id} onClick={() => request(t.id, latest.id)} title={`Request a run on ${latest.artifactName} ${latest.version}`}>{busy === t.id ? "Requesting…" : "Request run"}</button>
                      : <div className="text-xs"><span className="tag border-warn/60 text-warn">Not runnable here</span><div className="mt-1 text-muted">{t.unsupportedReason}</div></div>}
                  </td>
                </tr>
              ); })}
            </tbody>
          </table>
        </>);
      }}</QueryBoundary>
    </>
  );
}
