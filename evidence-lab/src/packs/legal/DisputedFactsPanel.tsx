import { Link } from "react-router-dom";
import type { LegalCheckRow } from "@/contracts";
import { computeEvidenceLabel, toUserFacingStatus } from "@/contracts";
import { EvidenceLabel, EmptyState, Marker } from "@/components";
import { byId } from "@/lib/lookup";
import type { PackPanelProps } from "../types";
import { DocLink } from "./docLink";

const RESULT: Record<LegalCheckRow["result"], { label: string; cls: string; glyph: string }> = {
  supported: { label: "Supported", cls: "border-ok/60 text-ok", glyph: "▲" }, unsupported: { label: "Unsupported", cls: "border-bad/60 text-bad", glyph: "▼" },
  match: { label: "Match", cls: "border-ok/60 text-ok", glyph: "▲" }, mismatch: { label: "Mismatch", cls: "border-bad/60 text-bad", glyph: "▼" },
  found: { label: "Contrary authority found", cls: "border-warn/60 text-warn", glyph: "●" }, none: { label: "None found", cls: "", glyph: "—" },
};

export function DisputedFactsPanel({ project, data }: PackPanelProps) {
  const runsById = byId(data.runs);
  const legalFindings = data.findings.filter((f) => f.packData?.packId === "legal");
  const latestRows = data.runs.filter((r) => r.status === "completed" && r.packData?.packId === "legal" && r.packData.rows?.length).sort((a, b) => b.sequence - a.sequence);
  return (
    <div className="space-y-4 text-sm" data-testid="disputed-facts">
      {legalFindings.length === 0 ? <EmptyState title="No disputed facts recorded" /> : legalFindings.map((f) => {
        const pd = f.packData?.packId === "legal" ? f.packData : null;
        const checks = data.checks.filter((c) => f.checkIds.includes(c.id));
        return (
          <div key={f.id} className="panel-2">
            <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{pd?.disputedFact ?? "Fact"}</span><EvidenceLabel label={computeEvidenceLabel(checks)} /><span className="tag">{toUserFacingStatus(f, runsById)}</span><Link className="ml-auto text-xs" to={`/p/${project.id}/findings/${f.id}`}>Open finding</Link></div>
            <p className="mt-1">{f.statement}</p>
            <div className="mt-1 flex flex-wrap gap-x-4 text-xs">
              {pd?.assertionLocation ? <span>Asserted at: <DocLink projectId={project.id} artifacts={data.artifacts} loc={pd.assertionLocation} /></span> : null}
              {pd?.sourceLocation ? <span>Source: <DocLink projectId={project.id} artifacts={data.artifacts} loc={pd.sourceLocation} /></span> : null}
            </div>
            {pd?.diff ? <div className="mt-2 grid gap-1 rounded bg-bg p-2 font-mono text-xs"><div><span className="text-bad">− quoted: </span>{pd.diff.quoted}</div><div><span className="text-ok">+ actual: </span>{pd.diff.actual}</div></div> : null}
          </div>
        );
      })}
      {latestRows.length > 0 ? (
        <div>
          <div className="h3 mb-1">Check rows from the latest runs <Marker kind="simulated" className="ml-1" /></div>
          <table className="tbl"><thead><tr><th>Run</th><th>Kind</th><th>Assertion</th><th>Result</th><th>Source location</th></tr></thead>
            <tbody>{latestRows.flatMap((r) => (r.packData?.packId === "legal" ? r.packData.rows ?? [] : []).map((row) => { const m = RESULT[row.result]; return (
              <tr key={`${r.id}-${row.id}`} data-testid="check-row" data-result={row.result}>
                <td><Link to={`/p/${project.id}/runs/${r.id}`}>#{r.sequence}</Link></td>
                <td className="text-xs text-muted">{row.kind.replace(/_/g, " ")}</td>
                <td>{row.assertion}<div className="text-xs text-muted">at <DocLink projectId={project.id} artifacts={data.artifacts} loc={row.assertionLocation} /></div>{row.detail ? <div className="text-xs text-faint">{row.detail}</div> : null}</td>
                <td><span className={`tag ${m.cls}`}>{m.glyph} {m.label}</span></td>
                <td className="text-xs">{row.sourceLocation ? <DocLink projectId={project.id} artifacts={data.artifacts} loc={row.sourceLocation} /> : "—"}</td>
              </tr>
            ); }))}</tbody></table>
        </div>
      ) : null}
    </div>
  );
}
