import { useMemo } from "react";
import { Link } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore } from "@/store";
import { useProject } from "@/shell/ProjectContext";
import type { WorkspacePanel, Run, AcceptanceCriteriaItem, Project, PackTemplate, PackId } from "@/contracts";
import { EmptyState, PageHeader, ProvenanceBadge, QueryBoundary, RunStatus } from "@/components";
import { fmtDateTime, fmtValue, humanize } from "@/lib/format";
import { latestTargetVersion, supersededIds, testName, versionLabel } from "@/lib/lookup";
import { PACK_PANELS } from "@/packs/registry";
import type { WorkspaceData } from "@/packs/types";

export function OverviewPage() {
  const { project, template } = useProject();
  const viewConfig = useAppStore((s) => s.viewConfig[project.id]);
  const q = useQuery(async () => {
    const [criteria, runs, tests, artifacts, approvals, tasks, audit, attacks, findings, checks] = await Promise.all([
      services.evidenceLab.listCriteria(project.id), services.evidenceLab.listRuns(project.id), services.evidenceLab.listTests(project.id),
      services.evidenceLab.listArtifacts(project.id), services.approvals.list(project.id), services.conductor.listTasks(project.id),
      services.evidenceLab.listAudit(project.id), services.evidenceLab.listAttackAssessments(project.id), services.evidenceLab.listFindings(project.id),
      services.evidenceLab.listChecks(project.id),
    ]);
    const d: WorkspaceData = { criteria, runs, tests, artifacts, approvals, tasks, audit, attacks, findings, checks };
    return d;
  }, [project.id]);

  const panels = useMemo(() => {
    const hidden = new Set(viewConfig?.hiddenPanels ?? []);
    const order = viewConfig?.panelOrder ?? [];
    const base = template.workspaceLayout.panels.filter((p) => !hidden.has(p.id));
    return [...base].sort((a, b) => { const ia = order.indexOf(a.id), ib = order.indexOf(b.id); return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib); });
  }, [template, viewConfig]);

  return (
    <>
      <PageHeader title={project.name} subtitle={<>{project.goal}</>} actions={<span className="tag">{humanize(project.status)}</span>}>
        <p className="mt-2 max-w-3xl text-sm">{project.summary}</p>
      </PageHeader>
      <QueryBoundary q={q} label="Loading workspace">{(d) => (
        <div className="grid gap-4 xl:grid-cols-2">
          {panels.map((p) => <Panel key={p.id} panel={p} data={d} project={project} template={template} />)}
          {(viewConfig?.hiddenPanels.length ?? 0) > 0 ? <div className="text-xs text-faint xl:col-span-2">{viewConfig?.hiddenPanels.length} panel(s) hidden by view configuration.</div> : null}
        </div>
      )}</QueryBoundary>
    </>
  );
}

type Data = WorkspaceData;

function Panel({ panel, data, project, template }: { panel: WorkspacePanel; data: Data; project: Project; template: PackTemplate }) {
  const wide = panel.kind === "metrics" || panel.kind === "pack_panel";
  const projectId = project.id;
  const PackComponent = panel.kind === "pack_panel" && panel.packComponent ? PACK_PANELS[panel.packComponent] : undefined;
  return (
    <section id={`panel-${panel.id}`} className={`panel ${wide ? "xl:col-span-2" : ""}`} data-testid={`panel-${panel.id}`} aria-labelledby={`panel-${panel.id}-title`}>
      <h2 id={`panel-${panel.id}-title`} className="h2 mb-3">{panel.title}</h2>
      {panel.kind === "metrics" ? <MetricsPanel data={data} projectId={projectId} criteriaVersion={project.currentCriteriaVersion} /> : null}
      {panel.kind === "pack_panel" ? (PackComponent ? <PackComponent project={project} template={template} data={data} /> : <EmptyState title={`No component is registered for "${panel.packComponent}".`} hint="Register it in src/packs/registry.tsx." />) : null}
      {panel.kind === "next_actions" ? <NextActions data={data} projectId={projectId} /> : null}
      {panel.kind === "untested" ? <Untested data={data} projectId={projectId} packId={project.packId} /> : null}
      {panel.kind === "activity" ? <Activity data={data} /> : null}
      {panel.kind === "disclaimer" ? <ul className="list-disc space-y-1 pl-4 text-sm text-muted" data-testid="disclaimers">{template.disclaimers.map((d) => <li key={d}>{d}</li>)}</ul> : null}
    </section>
  );
}

function latestRunFor(item: AcceptanceCriteriaItem, runs: Run[]): Run | null {
  const sup = supersededIds(runs);
  const candidates = runs.filter((r) => r.status === "completed" && !sup.has(r.id) && r.criteriaResults.some((c) => c.criteriaItemId === item.id));
  return candidates.length ? candidates.reduce((a, b) => (a.sequence >= b.sequence ? a : b)) : null;
}

function MetricsPanel({ data, projectId, criteriaVersion }: { data: Data; projectId: string; criteriaVersion: number }) {
  const crit = data.criteria.find((c) => c.version === criteriaVersion);
  if (!crit) return <EmptyState title="No approved acceptance criteria" hint="Metrics are only judged against an approved criteria version." />;
  return (
    <>
      <div className="mb-2 text-xs text-muted">Judged against acceptance criteria v{crit.version}. Each value links to the run that produced it and states how it was measured.</div>
      <table className="tbl">
        <thead><tr><th>Criterion</th><th>Latest value</th><th>Result</th><th>From</th></tr></thead>
        <tbody>
          {crit.items.map((item) => {
            const run = latestRunFor(item, data.runs);
            const res = run?.criteriaResults.find((c) => c.criteriaItemId === item.id);
            const metric = run?.metrics.find((m) => m.key === item.metric);
            return (
              <tr key={item.id} data-testid="metric-row">
                <td><div>{item.text}</div>{item.metric ? <div className="text-xs text-faint">{item.metric} {item.operator} {item.threshold}{item.unit ? ` ${item.unit}` : ""}</div> : null}</td>
                <td>{run && res ? <div className="flex flex-wrap items-center gap-1.5"><span className="font-mono">{fmtValue(res.observed, item.unit)}</span><ProvenanceBadge provenance={run.provenance} />{metric ? <span className="block w-full text-xs text-muted">{metric.definition}</span> : null}</div> : <span className="text-faint">not yet measured</span>}</td>
                <td>{res ? (res.pass === true ? <span className="tag border-ok/60 text-ok">▲ Pass</span> : res.pass === false ? <span className="tag border-bad/60 text-bad">▼ Fail</span> : <span className="tag">—</span>) : <span className="tag">Untested</span>}{res?.note ? <div className="text-xs text-muted">{res.note}</div> : null}</td>
                <td>{run ? <Link to={`/p/${projectId}/runs/${run.id}`}>Run #{run.sequence}</Link> : "—"}{run ? <div className="text-xs text-muted">{versionLabel(data.artifacts, run.artifactVersionId)}</div> : null}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

function NextActions({ data, projectId }: { data: Data; projectId: string }) {
  const pending = data.approvals.filter((a) => a.decision === "pending");
  const queued = data.runs.filter((r) => r.status === "queued" || r.status === "awaiting_approval");
  const blocked = data.tasks.filter((t) => t.status === "blocked" || t.status === "awaiting_checkpoint");
  const open = data.findings.filter((f) => !["closed", "not_relevant"].includes(f.status));
  const items: Array<{ key: string; text: React.ReactNode }> = [
    ...pending.map((a) => ({ key: a.id, text: <><Link to={`/p/${projectId}/approvals`}>Decide</Link>: {a.subjectLabel}</> })),
    ...queued.map((r) => ({ key: r.id, text: <><Link to={`/p/${projectId}/runs/${r.id}`}>Run #{r.sequence}</Link> is {humanize(r.status).toLowerCase()}</> })),
    ...blocked.map((t) => ({ key: t.id, text: <><Link to={`/p/${projectId}/conductor`}>{t.title}</Link> is {humanize(t.status).toLowerCase()}</> })),
    ...open.filter((f) => f.status !== "retested").map((f) => ({ key: f.id, text: <><Link to={`/p/${projectId}/findings/${f.id}`}>Finding</Link>: {f.statement.slice(0, 90)}…</> })),
  ];
  if (items.length === 0) return <EmptyState title="Nothing is waiting on you." />;
  return <ul className="list-disc space-y-1 pl-4 text-sm">{items.map((i) => <li key={i.key}>{i.text}</li>)}</ul>;
}

function Untested({ data, projectId, packId }: { data: Data; projectId: string; packId: PackId }) {
  const latestVersion = latestTargetVersion(packId, data.artifacts);
  const ranOnLatest = new Set(data.runs.filter((r) => r.status === "completed" && (!latestVersion || r.artifactVersionId === latestVersion.id)).map((r) => r.testDefinitionId));
  const notRunnable = data.tests.filter((t) => !t.runnable);
  const notYetRun = data.tests.filter((t) => t.runnable && !ranOnLatest.has(t.id));
  return (
    <div className="space-y-3 text-sm">
      {latestVersion ? <div className="text-xs text-muted">Relative to the latest artifact version: {versionLabel(data.artifacts, latestVersion.id)}.</div> : null}
      <div><div className="h3">Not runnable here</div>{notRunnable.length === 0 ? <div className="text-muted">—</div> : <ul className="mt-1 list-disc space-y-1 pl-4">{notRunnable.map((t) => <li key={t.id}><Link to={`/p/${projectId}/tests`}>{t.name}</Link><div className="text-xs text-muted">{t.unsupportedReason}</div></li>)}</ul>}</div>
      <div><div className="h3">Supported but not yet run on the latest version</div>{notYetRun.length === 0 ? <div className="text-muted">Every supported test has a completed run on the latest version.</div> : <ul className="mt-1 list-disc pl-4">{notYetRun.map((t) => <li key={t.id}>{testName(data.tests, t.id)}</li>)}</ul>}</div>
      <div className="text-xs text-faint">Anything not listed as a test was not tested. Absence of a finding is not evidence of absence.</div>
    </div>
  );
}

function Activity({ data }: { data: Data }) {
  const rows = data.audit.slice(0, 8);
  if (rows.length === 0) return <EmptyState title="No activity recorded" />;
  return (
    <ul className="space-y-1.5 text-sm" data-testid="activity">
      {rows.map((a) => <li key={a.id} className="flex flex-wrap gap-x-2"><span className="text-xs text-faint w-36 shrink-0">{fmtDateTime(a.timestamp)}</span><span className="text-muted">{a.actor.name}</span><span>{humanize(a.action.split(".").pop() ?? a.action).toLowerCase()}</span><span className="text-muted">· {a.subject.label}</span></li>)}
    </ul>
  );
}

export function LatestRunCell({ run }: { run: Run | null }) { return run ? <RunStatus run={run} /> : <span className="text-faint">—</span>; }
