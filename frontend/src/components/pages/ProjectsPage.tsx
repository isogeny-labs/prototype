import { useMemo, useState } from "react";
import { api, errorMessage, type Workspace, type WorkspaceProject } from "../../api";
import { DataTable, EmptyState, FilterSelect, PageHeader, SearchInput, Toolbar, type Column } from "../layout";
import { DemoDataLabel, ErrorBox, PrimaryButton, SecondaryButton, StatusChip, formatTime } from "../ui";
import { ActionsMenu, ClaimsCell, FixesCell, InlineForm, SystemsCell, TestsCell, folderLabel, folderOptions } from "./parts";

type Form =
  | { kind: "new-project" }
  | { kind: "new-folder" }
  | { kind: "rename-project"; project: WorkspaceProject }
  | { kind: "move-project"; project: WorkspaceProject }
  | { kind: "rename-folder"; id: number }
  | { kind: "move-folder"; id: number };

/** Home: every project with its latest assessment and that assessment's real counts. */
export function ProjectsPage({
  workspace,
  onChanged,
  onOpenAssessment,
  onLoadDemo,
  loadingDemo,
}: {
  workspace: Workspace;
  onChanged: () => Promise<void> | void;
  onOpenAssessment: (assessmentId: number, page?: "overview" | "inventory/import") => void;
  onLoadDemo: () => void;
  loadingDemo: boolean;
}) {
  const [query, setQuery] = useState("");
  const [folder, setFolder] = useState<string>("all");
  const [showArchived, setShowArchived] = useState(false);
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const archivedFolders = useMemo(() => {
    const ids = new Set<number>();
    for (const f of workspace.folders) if (f.archived) ids.add(f.id);
    return ids;
  }, [workspace]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return workspace.projects.filter((p) => {
      const hidden = p.archived || p.path.some((s) => archivedFolders.has(s.id));
      if (hidden && !showArchived) return false;
      if (folder !== "all") {
        const id = folder === "top" ? null : Number(folder);
        if (id === null ? p.folder_id !== null : !(p.folder_id === id || p.path.some((s) => s.id === id))) return false;
      }
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        p.path.some((s) => s.name.toLowerCase().includes(q)) ||
        (p.latest?.file?.filename.toLowerCase().includes(q) ?? false)
      );
    });
  }, [workspace, query, folder, showArchived, archivedFolders]);

  async function act(call: () => Promise<unknown>, after?: (result: unknown) => void) {
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      setForm(null);
      await onChanged();
      after?.(result);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const visibleProjects = workspace.projects.filter((p) => !p.archived);
  const selectedFolder = folder !== "all" && folder !== "top" ? workspace.folders.find((f) => f.id === Number(folder)) ?? null : null;

  const columns: Column<WorkspaceProject>[] = [
    {
      key: "project",
      header: "Project",
      render: (p) => (
        <div className="min-w-[12rem]">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-medium text-slate-100">
            {p.name}
            {p.archived ? <StatusChip size="sm" label="Archived" tone="neutral" /> : null}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>{p.path.length ? p.path.map((s) => s.name).join(" / ") : "Top level"}</span>
            {p.latest?.file?.is_demo ? <DemoDataLabel /> : null}
          </p>
        </div>
      ),
    },
    {
      key: "latest",
      header: "Latest assessment",
      render: (p) =>
        p.latest ? (
          <div className="min-w-[11rem]">
            <p className="flex items-center gap-2 text-slate-200">
              {p.latest.title}
              <StatusChip size="sm" label={p.latest.status.label} tone={p.latest.status.key === "open" ? "pass" : "neutral"} />
            </p>
            <p className="truncate text-xs text-slate-500">
              {p.latest.file ? p.latest.file.filename : "No file yet"} · {formatTime(p.latest.created_at)}
            </p>
          </div>
        ) : (
          <span className="text-slate-500">None</span>
        ),
    },
    { key: "claims", header: "Claims", className: "whitespace-nowrap", render: (p) => <ClaimsCell counts={p.counts} /> },
    { key: "tests", header: "Tests", className: "whitespace-nowrap", render: (p) => <TestsCell counts={p.counts} /> },
    { key: "fixes", header: "Fixes", className: "whitespace-nowrap", render: (p) => <FixesCell counts={p.counts} /> },
    { key: "systems", header: "Systems", className: "whitespace-nowrap", render: (p) => <SystemsCell counts={p.counts} /> },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "w-10 text-right",
      render: (p) => (
        <ActionsMenu
          label={`Actions for ${p.name}`}
          items={[
            { label: "Rename", onClick: () => setForm({ kind: "rename-project", project: p }) },
            { label: "Move to folder", onClick: () => setForm({ kind: "move-project", project: p }) },
            p.archived
              ? { label: "Unarchive", onClick: () => void act(() => api.changeProject(p.id, { archived: false })) }
              : { label: "Archive", onClick: () => void act(() => api.changeProject(p.id, { archived: true })) },
          ]}
        />
      ),
    },
  ];

  return (
    <div data-testid="projects-page">
      <PageHeader
        title="Projects"
        description="Each project keeps its own history of assessments. An assessment is one pass on one scanner file: import, verify, tests, evidence, fixes and migration."
        actions={
          <>
            <SecondaryButton onClick={() => setForm({ kind: "new-folder" })}>New folder</SecondaryButton>
            <PrimaryButton onClick={() => setForm({ kind: "new-project" })}>New project</PrimaryButton>
          </>
        }
      />
      {error && !form ? (
        <div className="mb-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      {form?.kind === "new-project" ? (
        <InlineForm
          title="New project"
          submitLabel="Create project"
          destination={{ label: "Folder", options: folderOptions(workspace), initial: selectedFolder ? String(selectedFolder.id) : "" }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(name, dest) =>
            void act(
              () => api.createProject(name, dest ? Number(dest) : null),
              (made) => onOpenAssessment((made as { assessment_id: number }).assessment_id, "inventory/import"),
            )
          }
        />
      ) : form?.kind === "new-folder" ? (
        <InlineForm
          title="New folder"
          submitLabel="Create folder"
          destination={{ label: "Inside", options: folderOptions(workspace), initial: selectedFolder ? String(selectedFolder.id) : "" }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(name, dest) => void act(() => api.createFolder(name, dest ? Number(dest) : null))}
        />
      ) : form?.kind === "rename-project" ? (
        <InlineForm
          title={`Rename ${form.project.name}`}
          submitLabel="Save name"
          initialName={form.project.name}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(name) => void act(() => api.changeProject(form.project.id, { name }))}
        />
      ) : form?.kind === "move-project" ? (
        <InlineForm
          title={`Move ${form.project.name}`}
          submitLabel="Move"
          nameLabel=""
          destination={{ label: "To folder", options: folderOptions(workspace), initial: form.project.folder_id ? String(form.project.folder_id) : "" }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(_name, dest) => void act(() => api.changeProject(form.project.id, { move: true, folder_id: dest ? Number(dest) : null }))}
        />
      ) : form?.kind === "rename-folder" ? (
        <InlineForm
          title="Rename folder"
          submitLabel="Save name"
          initialName={workspace.folders.find((f) => f.id === form.id)?.name}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(name) => void act(() => api.changeFolder(form.id, { name }))}
        />
      ) : form?.kind === "move-folder" ? (
        <InlineForm
          title={`Move ${folderLabel(workspace, form.id)}`}
          submitLabel="Move"
          nameLabel=""
          destination={{
            label: "Inside",
            options: folderOptions(workspace, { exclude: form.id }),
            initial: String(workspace.folders.find((f) => f.id === form.id)?.parent_id ?? ""),
          }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(_name, dest) => void act(() => api.changeFolder(form.id, { move: true, parent_id: dest ? Number(dest) : null }))}
        />
      ) : null}

      {visibleProjects.length === 0 && !showArchived ? (
        <EmptyState
          title="No projects yet"
          actions={
            <>
              <PrimaryButton onClick={() => setForm({ kind: "new-project" })}>New project</PrimaryButton>
              <SecondaryButton onClick={onLoadDemo} disabled={loadingDemo}>
                {loadingDemo ? "Loading demo projects…" : "Load demo projects"}
              </SecondaryButton>
            </>
          }
        >
          <p>
            A <strong className="text-slate-200">project</strong> is one system or product you look after, kept in folders as deep as you
            like. Each project keeps its history of <strong className="text-slate-200">assessments</strong>: one pass on one scanner file,
            from import and verify to tests, evidence, fixes and migration. Starting a new assessment never deletes the old one.
          </p>
          <p className="mt-2">Load demo projects adds one project for each demo file, with the file already imported.</p>
        </EmptyState>
      ) : (
        <>
          <Toolbar>
            <SearchInput value={query} onChange={setQuery} label="Search projects" />
            <FilterSelect
              label="Folder"
              value={folder}
              onChange={setFolder}
              options={[
                { value: "all", label: "All folders" },
                { value: "top", label: "Top level only" },
                ...folderOptions(workspace)
                  .filter((o) => o.value !== "")
                  .map((o) => ({ value: o.value, label: o.label })),
              ]}
            />
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Show archived
            </label>
            {selectedFolder ? (
              <ActionsMenu
                label={`Actions for folder ${selectedFolder.name}`}
                items={[
                  { label: "Rename folder", onClick: () => setForm({ kind: "rename-folder", id: selectedFolder.id }) },
                  { label: "Move folder", onClick: () => setForm({ kind: "move-folder", id: selectedFolder.id }) },
                  selectedFolder.archived
                    ? { label: "Unarchive folder", onClick: () => void act(() => api.changeFolder(selectedFolder.id, { archived: false })) }
                    : { label: "Archive folder", onClick: () => void act(() => api.changeFolder(selectedFolder.id, { archived: true })) },
                ]}
              />
            ) : null}
          </Toolbar>
          <DataTable
            label="Projects"
            columns={columns}
            rows={rows}
            rowKey={(p) => String(p.id)}
            rowTestId="project-row"
            onRowClick={(p) => p.latest && onOpenAssessment(p.latest.id)}
            empty="No project matches."
          />
          <p className="mt-3 text-xs text-slate-500">
            Counts come from each project's latest assessment, exactly as its pages show them. "Not yet" means that step has not
            happened in that assessment.
          </p>
        </>
      )}
    </div>
  );
}
