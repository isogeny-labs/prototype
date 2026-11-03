import { Link, useNavigate } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, EvidenceLabel, Marker, PageHeader, QueryBoundary } from "@/components";
import { computeEvidenceLabel, toUserFacingStatus } from "@/contracts";
import { humanize } from "@/lib/format";
import { byId } from "@/lib/lookup";

export function FindingsPage() {
  const { project, template } = useProject();
  const navigate = useNavigate();
  const q = useQuery(async () => ({ findings: await services.evidenceLab.listFindings(project.id), checks: await services.evidenceLab.listChecks(project.id), runs: await services.evidenceLab.listRuns(project.id) }), [project.id]);
  return (
    <>
      <PageHeader title="Findings" subtitle="Plain-language conclusions with a computed evidence label. The label comes from the checks on the finding, never from a hand-set field; only a deterministic check or a named reviewer raises it." />
      <QueryBoundary q={q} label="Loading findings">{({ findings, checks, runs }) => {
        const runsById = byId(runs);
        if (findings.length === 0) return <EmptyState title="No findings" hint="Findings open from failed runs, research or manual entry." />;
        return (
          <table className="tbl" data-testid="findings-table">
            <thead><tr><th>Finding</th><th>Label</th><th>Status</th><th>Origin</th><th>Evidence</th></tr></thead>
            <tbody>
              {findings.map((f) => { const fc = checks.filter((c) => f.checkIds.includes(c.id)); const label = computeEvidenceLabel(fc, { hasImportedEvidence: f.evidenceRunIds.some((id) => runsById[id]?.provenance === "imported") }); const status = toUserFacingStatus(f, runsById); return (
                <tr key={f.id} className="clickable" onClick={() => navigate(`/p/${project.id}/findings/${f.id}`)} data-testid="finding-row" data-status={status}>
                  <td><Link to={`/p/${project.id}/findings/${f.id}`} onClick={(e) => e.stopPropagation()}>{f.statement}</Link>{f.isSeeded ? <div className="mt-1"><Marker kind="sample" /> <span className="text-xs text-faint">planted sample defect</span></div> : null}{f.conflicts.some((c) => !c.resolved) ? <div className="mt-1 text-xs text-warn">⚠ Unresolved disagreement between agents</div> : null}</td>
                  <td><EvidenceLabel label={label} /></td>
                  <td><span className="tag">{status}</span></td>
                  <td className="text-xs text-muted">{humanize(f.origin)}</td>
                  <td className="text-xs text-muted">{fc.length} check{fc.length === 1 ? "" : "s"} · {f.evidenceRunIds.length} run{f.evidenceRunIds.length === 1 ? "" : "s"}{f.retestRunIds.length ? ` · ${f.retestRunIds.length} retest${f.retestRunIds.length === 1 ? "" : "s"}` : ""}</td>
                </tr>
              ); })}
            </tbody>
          </table>
        );
      }}</QueryBoundary>
      <div className="mt-4 text-xs text-faint">{template.disclaimers[0]}</div>
    </>
  );
}
