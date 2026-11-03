import { Link } from "react-router-dom";
import { EmptyState, Marker } from "@/components";
import { versionLabel } from "@/lib/lookup";
import type { PackPanelProps } from "../types";

export function ConvergencePanel({ project, data }: PackPanelProps) {
  const studies = data.runs.filter((r) => r.status === "completed" && r.packData?.packId === "engineering" && r.packData.convergenceLevels).sort((a, b) => a.sequence - b.sequence);
  if (studies.length === 0) return <EmptyState title="No convergence study yet" hint="A peak stress is reported as converged only after a study meets the criterion." />;
  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="convergence">
      {studies.map((run) => {
        if (run.packData?.packId !== "engineering" || !run.packData.convergenceLevels) return null;
        const levels = run.packData.convergenceLevels; const crit = run.packData.convergenceCriterionPercent ?? 5;
        const max = Math.max(...levels.map((l) => l.peakVonMisesMpa)) * 1.15;
        const ok = run.packData.converged === true;
        return (
          <div key={run.id} className="panel-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/p/${project.id}/runs/${run.id}`}>Run #{run.sequence}</Link><span className="text-muted">{versionLabel(data.artifacts, run.artifactVersionId)}</span>
              {ok ? <span className="tag border-ok/60 text-ok">▲ Converged</span> : <span className="tag border-bad/60 text-bad">▼ Not converged</span>}
              <span className="text-xs text-faint">criterion &lt; {crit}%</span><Marker kind="illustrative" className="ml-auto" />
            </div>
            <svg viewBox="0 0 320 120" className="mt-2 w-full rounded bg-bg" role="img" aria-label={`Peak von Mises per refinement level for run ${run.sequence}`}>
              {levels.map((l, i) => { const h = (l.peakVonMisesMpa / max) * 90; const x = 30 + i * 95; return (
                <g key={l.level}>
                  <rect x={x} y={100 - h} width="50" height={h} fill={l.changePercent !== null && l.changePercent >= crit ? "#F08A80" : "#76B8F4"} />
                  <text x={x + 25} y={96 - h} fill="#EDF1F7" fontSize="10" textAnchor="middle">{l.peakVonMisesMpa} MPa</text>
                  <text x={x + 25} y="113" fill="#A4B2C8" fontSize="9" textAnchor="middle">{l.elementSizeMm} mm · {(l.elements / 1000).toFixed(0)}k el.</text>
                  {l.changePercent !== null ? <text x={x + 25} y={86 - h} fill={l.changePercent >= crit ? "#F08A80" : "#5FCB8A"} fontSize="9" textAnchor="middle">{l.changePercent >= 0 ? "+" : ""}{l.changePercent}%</text> : null}
                </g>
              ); })}
            </svg>
            <table className="tbl mt-2"><thead><tr><th>Level</th><th>Fillet element size</th><th>Elements</th><th>Peak von Mises</th><th>Change</th></tr></thead>
              <tbody>{levels.map((l) => <tr key={l.level}><td>{l.level}</td><td>{l.elementSizeMm} mm</td><td>{l.elements.toLocaleString()}</td><td className="font-mono">{l.peakVonMisesMpa} MPa</td><td>{l.changePercent === null ? "—" : <span className={l.changePercent >= crit ? "text-bad" : "text-ok"}>{l.changePercent >= crit ? "▼" : "▲"} {l.changePercent}%</span>}</td></tr>)}</tbody></table>
          </div>
        );
      })}
    </div>
  );
}
