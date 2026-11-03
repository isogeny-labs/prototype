import { useProject } from "@/shell/ProjectContext";
import { PageHeader } from "@/components";
import { humanize } from "@/lib/format";

export function ProjectSettingsPage() {
  const { project, template } = useProject();
  return (
    <>
      <PageHeader title="Project settings" subtitle="Read-only in Phase 1. Permission and confidentiality changes go through a settings_change approval; the assistant cannot change them." />
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Members and roles</h2>
          <table className="tbl"><thead><tr><th>Person</th><th>Organisation</th><th>Role in project</th></tr></thead>
            <tbody>{project.permissions.members.map((m) => { const p = project.people.find((x) => x.id === m.personId); return <tr key={m.personId}><td>{p?.name ?? m.personId}<div className="text-xs text-muted">{p?.role}</div></td><td>{p?.org}</td><td><span className="tag">{m.role}</span></td></tr>; })}</tbody></table>
          <dl className="kv mt-3">
            <dt>Confidentiality</dt><dd>{humanize(project.permissions.confidentiality)}</dd>
            {project.permissions.notes ? <><dt>Notes</dt><dd className="text-muted">{project.permissions.notes}</dd></> : null}
          </dl>
        </section>
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Execution and template</h2>
          <dl className="kv">
            <dt>Execution mode</dt><dd>
              <div className="flex flex-col gap-1">
                {(["platform_sandbox", "customer_side"] as const).map((m) => <label key={m} className="flex items-center gap-2"><input type="radio" name="execution-mode" value={m} checked={project.executionMode === m} readOnly disabled /> <span>{humanize(m)}</span>{project.executionMode === m ? <span className="tag border-ok/60 text-ok">current</span> : null}<span className="tag border-warn/60 text-warn">Integration pending</span></label>)}
              </div>
              <div className="text-xs text-muted">Platform sandbox: allowlisted fixtures only (Docker runner unvalidated). Customer-side: runs on the customer's infrastructure with the customer-side runner. Neither is connected in this skeleton.</div>
            </dd>
            <dt>Template</dt><dd>{template.name} v{template.version} <span className="text-faint">({template.id})</span><div className="text-xs text-muted">{template.summary}</div></dd>
            <dt>Supported artifact types</dt><dd>{template.supportedArtifactTypes.join(", ")}</dd>
            <dt>Evidence requirements</dt><dd><ul className="list-disc pl-4">{template.evidenceRequirements.map((e) => <li key={e}>{e}</li>)}</ul></dd>
            <dt>Workspace controls</dt><dd>{template.workspaceLayout.controls.map((c) => <div key={c.id}><span className="font-medium">{c.label}</span> <span className="text-faint">({c.kind})</span>{c.description ? <span className="text-muted"> · {c.description}</span> : null}</div>)}</dd>
          </dl>
        </section>
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Integrations</h2>
          <table className="tbl"><thead><tr><th>Service</th><th>Role</th><th>Status</th></tr></thead>
            <tbody>
              {[["Runner (platform sandbox)", "Executes allowlisted test fixtures", "Mocked here · backend prototype exists"], ["Customer-side runner", "Executes tests on customer infrastructure", "Integration pending"], ["Autoresearcher", "Proposes bounded experiments", "Mocked here · has only run on cryptography"], ["Conductor (Go)", "Tasks, owners, budgets, checkpoints", "Not connected (separate repository)"], ["Cairn (Rust)", "Re-runnable checkers, signed checkpoints, evidence verification", "Not connected (separate repository)"], ["Assistant", "View configuration only", "Mocked here"]].map(([n, r, st]) => <tr key={n}><td>{n}</td><td className="text-muted">{r}</td><td><span className="tag border-warn/60 text-warn">{st}</span></td></tr>)}
            </tbody></table>
        </section>
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Budget</h2>
          <table className="tbl"><thead><tr><th>Resource</th><th>Used</th><th>Limit</th></tr></thead>
            <tbody>
              <tr><td>Time</td><td>{project.budget.timeHours.used} h</td><td>{project.budget.timeHours.limit} h</td></tr>
              <tr><td>Compute units <span className="text-xs text-faint">(one sandbox slot for one hour on the reference profile; sample definition)</span></td><td>{project.budget.computeUnits.used}</td><td>{project.budget.computeUnits.limit}</td></tr>
              <tr><td>Money</td><td>${project.budget.moneyUsd.used}</td><td>${project.budget.moneyUsd.limit}</td></tr>
            </tbody></table>
        </section>
      </div>
    </>
  );
}
