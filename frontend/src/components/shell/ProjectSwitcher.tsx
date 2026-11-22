import { useMemo, useRef, useState } from "react";
import type { Workspace, WorkspaceFolder, WorkspaceProject } from "../../api";
import { useDismiss } from "../ui";
import { Icon } from "./icons";

/** The project switcher: search plus the folder tree. Picking a project opens its latest assessment. Archived folders
 * and projects are hidden here (the Projects page can show them). */
export function ProjectSwitcher({
  workspace,
  currentProjectId,
  collapsed,
  onPick,
}: {
  workspace: Workspace | null;
  currentProjectId: number | null;
  collapsed: boolean;
  onPick: (project: WorkspaceProject) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useDismiss(open, box, () => setOpen(false));

  const current = workspace?.projects.find((p) => p.id === currentProjectId) ?? null;
  const visible = useMemo(() => {
    if (!workspace) return { folders: [] as WorkspaceFolder[], projects: [] as WorkspaceProject[] };
    const hiddenFolders = new Set<number>();
    // A folder is hidden when it, or a folder above it, is archived.
    for (const f of workspace.folders) {
      if (f.archived || f.path.some((p) => workspace.folders.find((x) => x.id === p.id)?.archived))
        hiddenFolders.add(f.id);
    }
    const q = query.trim().toLowerCase();
    const projects = workspace.projects.filter(
      (p) =>
        !p.archived &&
        (p.folder_id === null || !hiddenFolders.has(p.folder_id)) &&
        (!q || p.name.toLowerCase().includes(q) || p.path.some((s) => s.name.toLowerCase().includes(q))),
    );
    const used = new Set<number>();
    for (const p of projects) for (const s of p.path) used.add(s.id);
    const folders = workspace.folders.filter((f) => !hiddenFolders.has(f.id) && (!q || used.has(f.id)));
    return { folders, projects };
  }, [workspace, query]);

  function tree(parent: number | null, depth: number): React.ReactNode[] {
    const out: React.ReactNode[] = [];
    for (const f of visible.folders.filter((x) => x.parent_id === parent)) {
      out.push(
        <li
          key={`f${f.id}`}
          role="none"
          className="mt-1 flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-slate-500"
          style={{ paddingLeft: 8 + depth * 14 }}
        >
          <Icon name="folder" className="h-3.5 w-3.5" />
          {f.name}
        </li>,
      );
      out.push(...tree(f.id, depth + 1));
    }
    for (const p of visible.projects.filter((x) => x.folder_id === parent)) {
      out.push(
        <li key={`p${p.id}`} role="none">
          <button
            type="button"
            role="option"
            aria-selected={p.id === currentProjectId}
            onClick={() => {
              setOpen(false);
              setQuery("");
              onPick(p);
            }}
            className="flex w-full items-center gap-2 rounded-md py-1.5 pr-2 text-left text-sm text-slate-200 hover:bg-slate-800 aria-selected:bg-sky-400/10 aria-selected:text-slate-50"
            style={{ paddingLeft: 8 + depth * 14 }}
          >
            <Icon name="project" className="h-3.5 w-3.5 text-slate-500" />
            <span className="truncate">{p.name}</span>
          </button>
        </li>,
      );
    }
    return out;
  }

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Switch project${current ? `: ${current.name}` : ""}`}
        title={collapsed ? (current?.name ?? "Switch project") : undefined}
        onClick={() => setOpen((v) => !v)}
        className={`flex w-full items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 text-left text-sm text-slate-100 hover:border-slate-600 ${
          collapsed ? "justify-center p-2" : "px-2.5 py-2"
        }`}
      >
        <Icon name="project" className="h-4 w-4 text-slate-400" />
        {collapsed ? null : (
          <>
            <span className="min-w-0 flex-1 truncate">{current ? current.name : "Choose a project"}</span>
            <Icon name="chevron" className="h-3.5 w-3.5 text-slate-500" />
          </>
        )}
      </button>
      {open ? (
        <div
          data-testid="project-switcher"
          className="absolute left-0 top-full z-50 mt-1 w-72 rounded-xl border border-slate-700 bg-slate-950 p-2 shadow-2xl"
        >
          <label className="block">
            <span className="sr-only">Search projects</span>
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects"
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-500"
            />
          </label>
          <ul role="listbox" aria-label="Projects" className="quiet-scroll mt-1 max-h-80 overflow-y-auto">
            {tree(null, 0)}
          </ul>
          {visible.projects.length === 0 ? (
            <p className="px-2 py-3 text-sm text-slate-400">No project matches.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
