import { useState } from "react";
import { services, ServiceError } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, PageHeader, QueryBoundary, TaskGraph } from "@/components";
import type { Task } from "@/contracts";

export function ConductorPage() {
  const { project } = useProject();
  const q = useQuery(() => services.conductor.listTasks(project.id), [project.id]);
  const [msg, setMsg] = useState<string | null>(null);
  async function act(t: Task, action: "pause" | "resume" | "cancel") {
    setMsg(null);
    try { await services.conductor[action](project.id, t.id); setMsg(`${action} applied to "${t.title}" (simulated; Conductor is not connected).`); }
    catch (e) { setMsg(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
  }
  return (
    <>
      <PageHeader title="Conductor" subtitle="Task plan with dependencies, owners, budgets and checkpoints. Pause, resume and cancel are the only controls; checkpoints are decided on the Approvals page." />
      {msg ? <div className="callout-info mb-3" role="status">{msg}</div> : null}
      <QueryBoundary q={q} label="Loading tasks">{(tasks) => tasks.length === 0 ? <EmptyState title="No tasks planned" /> : (
        <TaskGraph tasks={tasks} projectId={project.id} actions={(t) => (<>
          {t.status === "queued" || t.status === "running" ? <button type="button" className="btn-ghost btn-sm" onClick={() => act(t, "pause")}>Pause</button> : null}
          {t.status === "paused" ? <button type="button" className="btn-ghost btn-sm" onClick={() => act(t, "resume")}>Resume</button> : null}
          {["queued", "running", "paused", "blocked", "awaiting_checkpoint"].includes(t.status) ? <button type="button" className="btn-danger btn-sm" onClick={() => act(t, "cancel")}>Cancel</button> : null}
        </>)} />
      )}</QueryBoundary>
      <div className="callout-sample mt-4 text-xs">Conductor (Go) lives in a separate repository and is not connected. Everything here is sample data; owners marked "Simulated" are not running.</div>
    </>
  );
}
