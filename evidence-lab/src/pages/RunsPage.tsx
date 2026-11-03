import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { useAppStore } from "@/store";
import { EmptyState, EvidenceLabel, ExecutionModeBadge, PageHeader, ProvenanceBadge, QueryBoundary, RunStatus } from "@/components";
import { fmtDateTime } from "@/lib/format";
import { runEvidenceLabel, supersededIds, testName, versionLabel } from "@/lib/lookup";

export function RunsPage() {
  const { project } = useProject();
  const navigate = useNavigate();
  const [showSuperseded, setShowSuperseded] = useState(true);
  const statusFilter = useAppStore((s) => s.viewConfig[project.id]?.filters["status"]);
  const q = useQuery(async () => ({
    runs: await services.evidenceLab.listRuns(project.id), tests: await services.evidenceLab.listTests(project.id),
    artifacts: await services.evidenceLab.listArtifacts(project.id), checks: await services.evidenceLab.listChecks(project.id),
  }), [project.id]);
  return (
    <>
      <PageHeader title="Runs" subtitle="Append-only. A corrected run supersedes the old one and says why; nothing is edited or deleted." actions={
        <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={showSuperseded} onChange={(e) => setShowSuperseded(e.target.checked)} /> Show superseded</label>} />
      <QueryBoundary q={q} label="Loading runs">{({ runs, tests, artifacts, checks }) => {
        const sup = supersededIds(runs);
        const byFilter = (r: (typeof runs)[number]) => !statusFilter || (statusFilter === "failed" ? r.status === "failed" || r.overallPass === false : statusFilter === "passed" ? r.overallPass === true : statusFilter === "completed" ? r.status === "completed" : statusFilter === "pending" ? ["queued", "running", "awaiting_approval"].includes(r.status) : true);
        const rows = [...runs].sort((a, b) => b.sequence - a.sequence).filter((r) => showSuperseded || !sup.has(r.id)).filter(byFilter);
        if (rows.length === 0) return <EmptyState title={statusFilter ? `No runs match the view filter "${statusFilter}"` : "No runs yet"} hint={statusFilter ? "Ask the assistant to reset the view." : "Request a run from the Tests page."} />;
        return (<>
          {statusFilter ? <div className="callout-info mb-2 text-xs" data-testid="view-filter-note">View filtered by the assistant: showing "{statusFilter}" runs ({rows.length} of {runs.length}). Ask it to "reset the view" to clear.</div> : null}
          <table className="tbl" data-testid="runs-table">
            <thead><tr><th>#</th><th>Test</th><th>Artifact version</th><th>Mode · provenance</th><th>Status</th><th>Label</th><th>When</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => navigate(`/p/${project.id}/runs/${r.id}`)} data-testid="run-row" data-superseded={sup.has(r.id)}>
                  <td className="font-mono"><Link to={`/p/${project.id}/runs/${r.id}`} onClick={(e) => e.stopPropagation()}>#{r.sequence}</Link></td>
                  <td>{testName(tests, r.testDefinitionId)}{r.supersedesRunId ? <div className="text-xs text-warn">corrects #{runs.find((x) => x.id === r.supersedesRunId)?.sequence ?? "?"}</div> : null}</td>
                  <td className="text-xs">{versionLabel(artifacts, r.artifactVersionId)}<div className="text-faint">criteria v{r.criteriaVersion}</div></td>
                  <td><div className="flex flex-wrap gap-1"><ExecutionModeBadge mode={r.executionMode} /><ProvenanceBadge provenance={r.provenance} /></div></td>
                  <td><RunStatus run={r} superseded={sup.has(r.id)} /></td>
                  <td>{(() => { const l = runEvidenceLabel(r, checks); return l ? <EvidenceLabel label={l} /> : <span className="text-xs text-faint" title="No result yet">—</span>; })()}</td>
                  <td className="text-xs text-muted">{fmtDateTime(r.finishedAt ?? r.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>);
      }}</QueryBoundary>
    </>
  );
}
