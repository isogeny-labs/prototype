import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { PageHeader, QueryBoundary } from "@/components";
import { fmtDateTime, humanize } from "@/lib/format";
import { actorName } from "@/lib/lookup";

export function IntakePage() {
  const { project, template } = useProject();
  const q = useQuery(async () => ({ criteria: await services.evidenceLab.listCriteria(project.id), approvals: await services.approvals.list(project.id) }), [project.id]);
  const statusCls = { open: "border-warn/60 text-warn", answered: "border-ok/60 text-ok", assumed: "border-info/60 text-info" } as const;
  return (
    <>
      <PageHeader title="Intake" subtitle="Goal, constraints, open questions and the acceptance criteria every run is judged against. Criteria versions are approved records; editing proposes a new version." />
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
              <div className="text-xs text-faint">Changing criteria proposes a new version and creates an approval request for the project owner (Phase 3 adds the form).</div>
            </div>
          )}</QueryBoundary>
        </section>
      </div>
    </>
  );
}
