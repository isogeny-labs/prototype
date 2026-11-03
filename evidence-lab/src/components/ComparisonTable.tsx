import type { Comparison, Run } from "@/contracts";
import { Link } from "react-router-dom";
import { fmtValue } from "@/lib/format";

export function ComparisonTable({ comparison, runsById, projectId }: { comparison: Comparison; runsById: Record<string, Run>; projectId: string }) {
  const b = runsById[comparison.baselineRunId]; const c = runsById[comparison.candidateRunId];
  const runLink = (r: Run | undefined, id: string) => r ? <Link to={`/p/${projectId}/runs/${r.id}`}>Run #{r.sequence}</Link> : <span>{id}</span>;
  return (
    <section className="panel text-sm" data-testid="comparison">
      <h3 className="h2">{comparison.title}</h3>
      <div className="mt-1 text-xs text-muted">Baseline {runLink(b, comparison.baselineRunId)} · Candidate {runLink(c, comparison.candidateRunId)}</div>
      <table className="tbl mt-3">
        <thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th><th>Regression?</th></tr></thead>
        <tbody>
          {comparison.metricDeltas.map((m) => (
            <tr key={m.key}>
              <td><div className="font-medium">{m.key}</div><div className="text-xs text-muted">{m.definition}</div></td>
              <td>{fmtValue(m.baseline)}</td>
              <td>{fmtValue(m.candidate)}</td>
              <td>{m.delta === null ? "—" : `${m.delta > 0 ? "+" : ""}${fmtValue(m.delta)}${m.deltaPercent === null ? "" : ` (${m.deltaPercent > 0 ? "+" : ""}${m.deltaPercent}%)`}`}</td>
              <td>{m.regression ? <span className="tag border-bad/60 text-bad">▼ Regression</span> : <span className="tag border-ok/60 text-ok">▲ No regression</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {comparison.previouslyFailingCases.length > 0 ? (
        <div className="mt-3">
          <div className="h3">Previously failing cases</div>
          <table className="tbl mt-1">
            <thead><tr><th>Case</th><th>Baseline</th><th>Candidate</th></tr></thead>
            <tbody>{comparison.previouslyFailingCases.map((pc) => (
              <tr key={pc.caseId}><td>{pc.caseId} · {pc.name}</td><td>{pc.baselinePass ? "pass" : <span className="text-bad">fail</span>}</td><td>{pc.candidatePass ? <span className="text-ok">pass</span> : <span className="text-bad">fail</span>}</td></tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <div><div className="h3">New regressions</div>{comparison.newRegressions.length === 0 ? <div className="text-muted">None observed in the compared runs.</div> : <ul className="list-disc pl-4">{comparison.newRegressions.map((r) => <li key={r}>{r}</li>)}</ul>}</div>
        <div><div className="h3">Remaining uncertainty</div><ul className="list-disc pl-4 text-muted">{comparison.remainingUncertainty.map((r) => <li key={r}>{r}</li>)}</ul></div>
        <div><div className="h3">Comparison limits</div><ul className="list-disc pl-4 text-muted">{comparison.comparisonLimits.map((r) => <li key={r}>{r}</li>)}</ul></div>
      </div>
    </section>
  );
}
