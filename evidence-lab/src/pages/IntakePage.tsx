import { useState } from "react";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import { PageHeader, QueryBoundary } from "@/components";
import type { AcceptanceCriteriaItem } from "@/contracts";
import { fmtDateTime, humanize } from "@/lib/format";
import { actorName } from "@/lib/lookup";

/** Editing criteria never changes the current version: it proposes a new one that needs the owner's approval. */
function ProposeCriteria({ projectId, base, onDone }: { projectId: string; base: AcceptanceCriteriaItem[]; onDone: (m: string) => void }) {
  const user = useAppStore((s) => s.user);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AcceptanceCriteriaItem[]>(() => base.map((i) => ({ ...i })));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const update = (idx: number, patch: Partial<AcceptanceCriteriaItem>) => setItems((xs) => xs.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  async function submit() {
    setBusy(true); setErr(null);
    try { const r = await services.evidenceLab.proposeCriteriaVersion(projectId, items, user.id); onDone(`Proposed acceptance criteria v${r.criteria.version}. It awaits the owner's approval; runs keep being judged against v${r.criteria.version - 1} until then.`); setOpen(false); }
    catch (e) { setErr(e instanceof ServiceError ? e.message : String(e)); } finally { setBusy(false); }
  }
  if (!open) return <button type="button" className="btn-ghost btn-sm" onClick={() => setOpen(true)} data-testid="propose-criteria">Propose a new version</button>;
  return (
    <div className="panel-2 mt-3 text-sm" data-testid="propose-criteria-form">
      <div className="h3 mb-2">New version (proposal)</div>
      <table className="tbl"><thead><tr><th>Id</th><th>Criterion</th><th>Metric</th><th>Op</th><th>Threshold</th><th>Unit</th></tr></thead>
        <tbody>{items.map((it, i) => <tr key={it.id}><td className="font-mono text-xs">{it.id}</td><td><input className="input" value={it.text} onChange={(e) => update(i, { text: e.target.value })} aria-label={`Criterion ${it.id} text`} /></td><td><input className="input" value={it.metric ?? ""} onChange={(e) => update(i, { metric: e.target.value || undefined })} /></td><td><select className="input" value={it.operator ?? ""} onChange={(e) => update(i, { operator: (e.target.value || undefined) as AcceptanceCriteriaItem["operator"] })}><option value="">—</option>{["<=", ">=", "==", "<", ">"].map((o) => <option key={o} value={o}>{o}</option>)}</select></td><td><input className="input" type="number" step="any" value={it.threshold ?? ""} onChange={(e) => update(i, { threshold: e.target.value === "" ? undefined : Number(e.target.value) })} aria-label={`Criterion ${it.id} threshold`} /></td><td><input className="input" value={it.unit ?? ""} onChange={(e) => update(i, { unit: e.target.value || undefined })} /></td></tr>)}</tbody></table>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className="btn-ghost btn-sm" onClick={() => setItems((xs) => [...xs, { id: `ac-new-${xs.length + 1}`, text: "" }])}>Add item</button>
        <button type="button" className="btn btn-sm" disabled={busy || items.some((x) => !x.text.trim())} onClick={submit} data-testid="propose-criteria-submit">Submit for approval</button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {err ? <div className="callout-bad mt-2 text-xs" role="alert">{err}</div> : null}
    </div>
  );
}

export function IntakePage() {
  const { project, template } = useProject();
  const [msg, setMsg] = useState<string | null>(null);
  const q = useQuery(async () => ({ criteria: await services.evidenceLab.listCriteria(project.id), approvals: await services.approvals.list(project.id) }), [project.id]);
  const statusCls = { open: "border-warn/60 text-warn", answered: "border-ok/60 text-ok", assumed: "border-info/60 text-info" } as const;
  return (
    <>
      <PageHeader title="Intake" subtitle="Goal, constraints, open questions and the acceptance criteria every run is judged against. Criteria versions are approved records; editing proposes a new version." />
      {msg ? <div className="callout-ok mb-3 text-sm" role="status" data-testid="intake-message">{msg}</div> : null}
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Goal</h2><p>{project.goal}</p>
          <h2 className="h2 mb-2 mt-4">Constraints</h2><ul className="list-disc space-y-1 pl-4">{project.constraints.map((c) => <li key={c}>{c}</li>)}</ul>
          <dl className="kv mt-4">
            <dt>Pack / template</dt><dd>{humanize(project.packId)} · {template.name} v{template.version}</dd>
            <dt>Execution mode</dt><dd>{humanize(project.executionMode)}</dd>
            <dt>Budget</dt><dd>{project.budget.timeHours.used}/{project.budget.timeHours.limit} h · {project.budget.computeUnits.used}/{project.budget.computeUnits.limit} compute units · ${project.budget.moneyUsd.used}/${project.budget.moneyUsd.limit}<div className="text-xs text-faint">Compute unit: one sandbox slot for one hour on the reference profile (sample definition).</div></dd>
            <dt>Created</dt><dd>{fmtDateTime(project.createdAt)}</dd>
          </dl>
        </section>
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Intake questions</h2>
          <ul className="space-y-2">
            {project.intakeQuestions.map((iq) => (
              <li key={iq.id} className="panel-2" data-testid="intake-question">
                <div className="flex items-center gap-2"><span className={`tag ${statusCls[iq.status]}`}>{iq.status}</span><span className="font-medium">{iq.question}</span></div>
                {iq.answer ? <div className="mt-1 text-muted">{iq.answer}</div> : null}
                {iq.assumption ? <div className="mt-1 text-muted"><span className="font-semibold text-info">Assumption used:</span> {iq.assumption}</div> : null}
                {iq.status === "open" ? <div className="mt-1 text-faint">Unanswered. Findings that depend on it say so in their limitations.</div> : null}
              </li>
            ))}
          </ul>
        </section>
        <section className="panel text-sm xl:col-span-2">
          <h2 className="h2 mb-2">Acceptance criteria</h2>
          <QueryBoundary q={q} label="Loading criteria">{({ criteria, approvals }) => (
            <div className="space-y-4">
              {[...criteria].sort((a, b) => b.version - a.version).map((c) => { const apr = approvals.find((a) => a.id === c.approvalId) ?? approvals.find((a) => a.subjectType === "acceptance_criteria" && a.subjectId === c.id); return (
                <div key={c.id} data-testid="criteria-version">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">Version {c.version}</span>
                    {c.version === project.currentCriteriaVersion ? <span className="tag border-ok/60 text-ok">Current</span> : null}
                    {c.approvalId ? <span className="tag border-ok/60 text-ok">✓ Approved{apr?.reviewerId ? ` by ${actorName(project, apr.reviewerId)}` : ""}</span> : <span className="tag border-warn/60 text-warn">◷ Awaiting approval</span>}
                    <span className="text-xs text-faint">proposed by {actorName(project, c.createdBy)} · {fmtDateTime(c.createdAt)}{c.supersedesVersion ? ` · supersedes v${c.supersedesVersion}` : ""}</span>
                  </div>
                  <table className="tbl mt-2">
                    <thead><tr><th>Id</th><th>Criterion</th><th>Machine-checkable rule</th></tr></thead>
                    <tbody>{c.items.map((it) => <tr key={it.id}><td className="font-mono text-xs">{it.id}</td><td>{it.text}</td><td className="font-mono text-xs">{it.metric ? `${it.metric} ${it.operator} ${it.threshold}${it.unit ? ` ${it.unit}` : ""}` : <span className="text-faint">manual</span>}</td></tr>)}</tbody>
                  </table>
                </div>
              ); })}
              <div className="text-xs text-faint">Changing criteria proposes a new version and creates an approval request for the project owner.</div>
              <ProposeCriteria projectId={project.id} base={criteria.find((c) => c.version === project.currentCriteriaVersion)?.items ?? []} onDone={setMsg} />
            </div>
          )}</QueryBoundary>
        </section>
      </div>
    </>
  );
}
