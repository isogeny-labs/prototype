import type { PackPanelProps } from "../types";
import { Marker } from "@/components";

export function ModelSetupPanel({ project }: PackPanelProps) {
  if (project.packData.packId !== "engineering") return null;
  const m = project.packData.modelSetup;
  return (
    <div className="grid gap-4 text-sm md:grid-cols-2" data-testid="model-setup">
      <div className="min-w-0">
        <div className="h3">Part</div><div>{m.partName}</div>
        <div className="h3 mt-3">Material <Marker kind="sample" className="ml-1" /></div>
        <dl className="kv mt-1">
          <dt>Name</dt><dd>{m.material.name}</dd>
          <dt>Yield strength</dt><dd>{m.material.yieldMpa} MPa</dd>
          <dt>Young's modulus</dt><dd>{m.material.youngsModulusGpa} GPa</dd>
          <dt>Poisson's ratio</dt><dd>{m.material.poissonRatio}</dd>
          <dt>Density</dt><dd>{m.material.densityKgM3} kg/m³</dd>
          <dt>Source</dt><dd className="text-muted">{m.material.source}</dd>
        </dl>
        <div className="h3 mt-3">Acceptance</div>
        <div>Safety factor ≥ {m.acceptance.requiredSafetyFactor.toFixed(1)} against {m.acceptance.basis}; convergence change &lt; {m.acceptance.convergenceCriterionPercent}% between the last two refinement levels.</div>
      </div>
      <div className="min-w-0">
        <div className="h3">Loads</div>
        <ul className="mt-1 space-y-1">{m.loads.map((l) => <li key={l.id}><span className="font-mono text-xs">{l.id}</span> {l.description}: <strong>{l.magnitude}</strong><div className="text-xs text-muted">{l.location}</div></li>)}</ul>
        <div className="h3 mt-3">Boundary conditions</div>
        <ul className="mt-1 space-y-1">{m.boundaryConditions.map((b) => <li key={b.id}><span className="font-mono text-xs">{b.id}</span> {b.description}</li>)}</ul>
        <div className="h3 mt-3">Solver and assumptions</div>
        <div>{m.solver.label} · {m.solver.elementType}</div>
        <ul className="mt-1 flex flex-wrap gap-1">{m.solver.assumptions.map((a) => <li key={a} className="tag">{a}</li>)}</ul>
      </div>
    </div>
  );
}
