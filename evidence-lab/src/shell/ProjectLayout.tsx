import { Outlet } from "react-router-dom";
import { useProjectCtx } from "./ProjectContext";
import { ErrorState, LoadingState } from "@/components";

/** Guards every /p/:id route: renders children only once the project and its template are loaded. */
export function ProjectLayout() {
  const ctx = useProjectCtx();
  if (ctx.status === "failed") return <ErrorState title="Couldn't load this project" message={ctx.error ?? "Unknown error"} onRetry={ctx.retry} />;
  if (!ctx.project || !ctx.template) return <LoadingState label="Loading project" />;
  return <Outlet />;
}
