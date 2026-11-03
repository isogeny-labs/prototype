import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { ApprovalCard, EmptyState, PageHeader, QueryBoundary } from "@/components";

export function ApprovalsPage() {
  const { project, template } = useProject();
  const q = useQuery(() => services.approvals.list(project.id), [project.id]);
  return (
    <>
      <PageHeader title="Approvals" subtitle="Every decision is a record with who, when and why. Requesters cannot decide their own requests. Decision controls arrive in Phase 3; this view shows the records and the template's gates." />
      <QueryBoundary q={q} label="Loading approvals">{(approvals) => {
        const pending = approvals.filter((a) => a.decision === "pending");
        const decided = approvals.filter((a) => a.decision !== "pending").sort((a, b) => ((a.decidedAt ?? "") < (b.decidedAt ?? "") ? 1 : -1));
        return (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <div>
              <h2 className="h3 mb-2">Pending ({pending.length})</h2>
              {pending.length === 0 ? <EmptyState title="Nothing pending" /> : <div className="grid gap-3">{pending.map((a) => <ApprovalCard key={a.id} approval={a} project={project} />)}</div>}
              <h2 className="h3 mb-2 mt-6">Decided ({decided.length})</h2>
              {decided.length === 0 ? <EmptyState title="No decisions yet" /> : <div className="grid gap-3">{decided.map((a) => <ApprovalCard key={a.id} approval={a} project={project} />)}</div>}
            </div>
            <aside className="panel text-sm self-start">
              <h2 className="h2 mb-2">Approval gates in {template.name} v{template.version}</h2>
              <ul className="space-y-2">{template.approvalGates.map((g) => <li key={g.id}><div className="font-medium">{g.subjectType.replace(/_/g, " ")} <span className="tag ml-1">{g.requiredRole}</span></div><div className="text-muted">{g.description}</div></li>)}</ul>
            </aside>
          </div>
        );
      }}</QueryBoundary>
    </>
  );
}
