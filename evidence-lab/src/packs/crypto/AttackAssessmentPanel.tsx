import { useState } from "react";
import { Link } from "react-router-dom";
import type { AttackAssessment } from "@/contracts";
import { EmptyState, Marker } from "@/components";
import type { PackPanelProps } from "../types";

const CATEGORY: Record<AttackAssessment["category"], { label: string; cls: string }> = {
  reproduced_weakness: { label: "Reproduced weakness", cls: "border-bad/60 text-bad" },
  measured_experiment: { label: "Measured experiment", cls: "border-ok/60 text-ok" },
  estimate_with_assumptions: { label: "Estimate with assumptions", cls: "border-warn/60 text-warn" },
  published_estimate: { label: "Published estimate", cls: "border-info/60 text-info" },
  no_defensible_estimate: { label: "No defensible estimate", cls: "border-muted/60 text-muted" },
};

export function AttackAssessmentPanel({ project, data }: PackPanelProps) {
  const [model, setModel] = useState<"both" | "classical" | "quantum">("both");
  const rows = data.attacks.filter((a) => model === "both" || a.attackModel === model);
  if (data.attacks.length === 0) return <EmptyState title="No attack assessments recorded" />;
  return (
    <>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-muted">
        <label>Attack model <select className="input ml-1 w-auto" value={model} onChange={(e) => setModel(e.target.value as typeof model)} data-testid="attack-model"><option value="both">both</option><option value="classical">classical</option><option value="quantum">quantum</option></select></label>
        <span>Each row says what kind of statement it is. Nothing here is a single score.</span>
        <Marker kind="sample" className="ml-auto" />
      </div>
      <table className="tbl">
        <thead><tr><th>Kind of statement</th><th>Target / objective</th><th>Method and source</th><th>Expected work</th><th>Uncertainty</th></tr></thead>
        <tbody>
          {rows.map((a) => { const run = a.linkedRunId ? data.runs.find((r) => r.id === a.linkedRunId) : null; const c = CATEGORY[a.category]; return (
            <tr key={a.id} data-testid="attack-row" data-category={a.category}>
              <td><span className={`tag ${c.cls}`}>{c.label}</span><div className="mt-1 text-xs text-faint">{a.attackModel} · reviewed {a.reviewDate}{a.backendCategory ? ` · category ${a.backendCategory}` : ""}</div></td>
              <td><div>{a.target}</div><div className="text-xs text-muted">{a.objective}</div></td>
              <td><div>{a.method}</div><div className="text-xs text-muted">{a.source}{run ? <> · <Link to={`/p/${project.id}/runs/${run.id}`}>Run #{run.sequence}</Link></> : null}</div>{a.assumptions.length ? <div className="mt-1 text-xs text-faint">Assumes: {a.assumptions.join(" ")}</div> : null}</td>
              <td>{a.expectedWork}</td>
              <td className="text-muted">{a.uncertainty}</td>
            </tr>
          ); })}
        </tbody>
      </table>
    </>
  );
}
