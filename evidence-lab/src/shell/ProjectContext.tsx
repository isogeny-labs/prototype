import { createContext, useContext } from "react";
import type { PackTemplate, Project } from "@/contracts";

export interface ProjectCtx {
  projectId: string | null;
  project: Project | null;
  template: PackTemplate | null;
  status: "idle" | "loading" | "ready" | "failed";
  error: string | null;
  retry: () => void;
}

export const ProjectContext = createContext<ProjectCtx>({ projectId: null, project: null, template: null, status: "idle", error: null, retry: () => {} });
export function useProjectCtx(): ProjectCtx { return useContext(ProjectContext); }

/** For pages inside /p/:id: the project is guaranteed loaded by ProjectLayout. */
export function useProject(): { project: Project; template: PackTemplate } {
  const ctx = useContext(ProjectContext);
  if (!ctx.project || !ctx.template) throw new Error("useProject must be used under a loaded ProjectLayout");
  return { project: ctx.project, template: ctx.template };
}
