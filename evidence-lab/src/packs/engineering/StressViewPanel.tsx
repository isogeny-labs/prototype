import { useState } from "react";
import { Link } from "react-router-dom";
import type { Run, StressRegion } from "@/contracts";
import { EmptyState, Marker } from "@/components";
import { supersededIds, versionLabel } from "@/lib/lookup";
import type { PackPanelProps } from "../types";

/** Blue (low) to red (high) on a fixed 0..max scale. Every region is also labelled with its value: never colour alone. */
function colourFor(v: number, max: number): string {
  const t = Math.max(0, Math.min(1, v / max));
  const stops: Array<[number, [number, number, number]]> = [[0, [48, 92, 170]], [0.35, [72, 170, 150]], [0.6, [232, 184, 109]], [0.8, [235, 120, 80]], [1, [214, 60, 60]]];
  let a = stops[0]!, b = stops[stops.length - 1]!;
  for (let i = 0; i < stops.length - 1; i++) { const s0 = stops[i]!, s1 = stops[i + 1]!; if (t >= s0[0] && t <= s1[0]) { a = s0; b = s1; break; } }
  const u = b[0] === a[0] ? 0 : (t - a[0]) / (b[0] - a[0]);
  const c = a[1].map((x, i) => Math.round(x + (b[1][i]! - x) * u));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

export function StressViewPanel({ project, data }: PackPanelProps) {
  const [which, setWhich] = useState<"latest" | string>("latest");
  const sup = supersededIds(data.runs);
  const staticRuns = data.runs.filter((r) => r.status === "completed" && !sup.has(r.id) && r.packData?.packId === "engineering" && r.packData.stressRegions);
  const versions = [...new Set(staticRuns.map((r) => r.artifactVersionId))];
  const run: Run | undefined = which === "latest" ? staticRuns.sort((a, b) => b.sequence - a.sequence)[0] : staticRuns.filter((r) => r.artifactVersionId === which).sort((a, b) => b.sequence - a.sequence)[0];
  if (!run || run.packData?.packId !== "engineering" || !run.packData.stressRegions) return <EmptyState title="No static run with a stress map yet" />;
  const regions = run.packData.stressRegions;
  const yieldMpa = project.packData.packId === "engineering" ? project.packData.modelSetup.material.yieldMpa : 276;
  const max = Math.max(yieldMpa * 0.75, ...regions.map((r) => r.vonMisesMpa));
  const v = (id: StressRegion["id"]) => regions.find((r) => r.id === id);
  const fill = (id: StressRegion["id"]) => colourFor(v(id)?.vonMisesMpa ?? 0, max);
  const peak = regions.reduce((a, b) => (a.vonMisesMpa >= b.vonMisesMpa ? a : b));
  const sf = run.metrics.find((m) => m.key === "safety_factor");
  return (
    <div data-testid="stress-view">
      <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-muted">
        <label>Geometry version <select className="input ml-1 w-auto" value={which} onChange={(e) => setWhich(e.target.value)} data-testid="stress-version">
          <option value="latest">latest run</option>
          {versions.map((id) => <option key={id} value={id}>{versionLabel(data.artifacts, id)}</option>)}
        </select></label>
        <span>Showing <Link to={`/p/${project.id}/runs/${run.id}`}>Run #{run.sequence}</Link> on {versionLabel(data.artifacts, run.artifactVersionId)}. Schematic placeholder, not the geometry: region colours and labels come from the run's stress table.</span>
        <Marker kind="illustrative" className="ml-auto" />
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <svg viewBox="0 0 420 260" role="img" aria-label={`Schematic bracket with von Mises stress by region; peak ${peak.vonMisesMpa} MPa at ${peak.label}`} className="w-full max-w-2xl rounded bg-bg">
          <rect x="40" y="20" width="44" height="220" rx="4" fill={fill("plate")} stroke="#29364A" />
          <rect x="84" y="150" width="276" height="44" rx="4" fill={fill("arm_mid")} stroke="#29364A" />
          <rect x="84" y="150" width="70" height="44" fill={fill("arm_root")} stroke="#29364A" />
          <rect x="300" y="150" width="60" height="44" rx="4" fill={fill("arm_tip")} stroke="#29364A" />
          <path d="M 84 150 Q 84 128 106 128 L 106 150 Z" fill={fill("fillet")} stroke="#29364A" />
          <circle cx="62" cy="52" r="9" fill="#080C12" stroke={fill("bolt_holes")} strokeWidth="4" />
          <circle cx="62" cy="208" r="9" fill="#080C12" stroke={fill("bolt_holes")} strokeWidth="4" />
          <line x1="340" y1="110" x2="340" y2="146" stroke="#EDF1F7" strokeWidth="2" markerEnd="url(#arrow)" />
          <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="6" orient="auto"><path d="M0,0 L8,0 L4,8 z" fill="#EDF1F7" /></marker></defs>
          <text x="348" y="104" fill="#EDF1F7" fontSize="11">2.0 kN</text>
          <text x="20" y="52" fill="#A4B2C8" fontSize="9" textAnchor="end">fixed</text>
          <text x="20" y="208" fill="#A4B2C8" fontSize="9" textAnchor="end">fixed</text>
          <text x="62" y="134" fill="#EDF1F7" fontSize="10" textAnchor="middle">{v("plate")?.vonMisesMpa} MPa</text>
          <text x="119" y="178" fill="#06101A" fontSize="10" textAnchor="middle" fontWeight="700">{v("arm_root")?.vonMisesMpa}</text>
          <text x="230" y="178" fill="#06101A" fontSize="10" textAnchor="middle" fontWeight="700">{v("arm_mid")?.vonMisesMpa} MPa</text>
          <text x="330" y="178" fill="#EDF1F7" fontSize="10" textAnchor="middle">{v("arm_tip")?.vonMisesMpa}</text>
          <text x="96" y="122" fill="#EDF1F7" fontSize="11" fontWeight="700">fillet {v("fillet")?.vonMisesMpa} MPa (peak)</text>
          <text x="80" y="52" fill="#EDF1F7" fontSize="10">holes {v("bolt_holes")?.vonMisesMpa} MPa</text>
          <g transform="translate(40 246)">
            {Array.from({ length: 24 }, (_, i) => <rect key={i} x={i * 10} y="0" width="10" height="8" fill={colourFor((i / 23) * max, max)} />)}
            <text x="0" y="-3" fill="#A4B2C8" fontSize="9">0</text>
            <text x="240" y="-3" fill="#A4B2C8" fontSize="9" textAnchor="end">{Math.round(max)} MPa von Mises</text>
          </g>
        </svg>
        <div className="text-sm">
          <table className="tbl"><thead><tr><th>Region</th><th>von Mises</th></tr></thead>
            <tbody>{[...regions].sort((a, b) => b.vonMisesMpa - a.vonMisesMpa).map((r) => <tr key={r.id}><td><span aria-hidden="true" className="mr-2 inline-block h-3 w-3 rounded-sm align-middle" style={{ background: colourFor(r.vonMisesMpa, max) }} />{r.label}{r.id === peak.id ? <span className="tag ml-2 border-bad/60 text-bad">peak</span> : null}</td><td className="font-mono">{r.vonMisesMpa} MPa</td></tr>)}</tbody></table>
          <div className="mt-2 text-xs text-muted">Yield {yieldMpa} MPa. Safety factor {sf ? String(sf.value) : "—"} = {yieldMpa} / {peak.vonMisesMpa}. {run.packData.peakLocation}{run.packData.converged === false ? " · not mesh-converged" : run.packData.converged ? " · mesh-converged" : ""}.</div>
        </div>
      </div>
    </div>
  );
}
