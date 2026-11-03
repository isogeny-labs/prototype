import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, PageHeader, QueryBoundary } from "@/components";
import { fmtDateTime, humanize } from "@/lib/format";

export function MemoryPage() {
  const { project } = useProject();
  const q = useQuery(async () => ({ memory: await services.learning.listMemory(project.id), config: await services.learning.listAgentConfigChanges(project.id), training: await services.learning.listModelTraining() }), [project.id]);
  return (
    <>
      <PageHeader title="Memory" subtitle="Three things that must never be conflated: organisational memory (customer-scoped records written by decisions), agent configuration changes (proposed, evaluated, approved), and model training (not in MVP)." />
      <div className="callout-info mb-4 text-xs">How records get here: approving a recommendation writes an <em>accepted finding</em>; rejecting a proposal writes a <em>rejected hypothesis</em>; requesting changes on a recommendation with a note writes an <em>expert correction</em>; approving a protocol writes an <em>approved configuration</em>. Nothing here is edited by hand, and nothing here retrains a model.</div>
      <QueryBoundary q={q} label="Loading memory">{({ memory, config, training }) => (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="panel text-sm">
            <h2 className="h2 mb-2">Organisational memory</h2>
            {memory.length === 0 ? <EmptyState title="Nothing recorded yet" /> : <ul className="space-y-2">{memory.map((m) => <li key={m.id} className="panel-2" data-testid="memory-item"><div className="flex flex-wrap items-center gap-2"><span className="tag">{humanize(m.kind)}</span><span className="tag border-ivory/60 text-ivory">scope: {m.customerScope}</span><span className="ml-auto text-xs text-faint">{fmtDateTime(m.recordedAt)}</span></div><div className="mt-1">{m.text}</div><div className="mt-1 text-xs text-muted">source: {m.sourceRef.kind} {m.sourceRef.id} · recorded by {m.recordedBy}</div></li>)}</ul>}
          </section>
          <section className="panel text-sm">
            <h2 className="h2 mb-2">Agent configuration changes</h2>
            {config.length === 0 ? <EmptyState title="No configuration changes proposed" /> : <ul className="space-y-2">{config.map((c) => <li key={c.id} className="panel-2" data-testid="agent-config-change"><div className="flex flex-wrap items-center gap-2"><span className="tag">{c.target}</span><span className="tag border-warn/60 text-warn">{humanize(c.evaluationStatus)}</span><span className="text-xs text-muted">{c.agentName}</span></div><div className="mt-1">{c.proposedChange}</div><div className="mt-1 text-xs text-muted">Why: {c.rationale}</div><div className="text-xs text-faint">Evaluated and approved before use; see Approvals.</div></li>)}</ul>}
            <h2 className="h2 mb-2 mt-4">Model training</h2>
            {training.map((t) => <div key={t.id} className="callout-info"><strong>Not in MVP.</strong> {t.note}</div>)}
          </section>
        </div>
      )}</QueryBoundary>
    </>
  );
}
