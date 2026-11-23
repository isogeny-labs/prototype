import { useEffect, useState } from "react";
import {
  api,
  errorMessage,
  type OttoProjectBlock,
  type ProjectOverview,
  type ProjectOverviewRow,
  type Workspace,
} from "../../api";
import { linkRoute, routeHref } from "../../router";
import { DataTable, FilterSelect, PageHeader, type Column } from "../layout";
import { ErrorBox, SecondaryButton, StatusChip, formatTime } from "../ui";
import {
  ActionsMenu,
  ClaimsCell,
  FixesCell,
  InlineForm,
  Section,
  SystemsCell,
  TestsCell,
  folderOptions,
} from "./parts";

/** The three columns of the block below, on a screen wide enough for columns: the assessment, how many proposals wait
 * in it, and what changed since the pack. */
const OTTO_COLS = "md:grid-cols-[minmax(9rem,14rem)_minmax(9rem,16rem)_minmax(0,1fr)]";

/** Phase 5c: Otto in this project. For each assessment: how many of Otto's proposals wait for a decision there, and
 * what changed since the newest test pack was installed. Every word and count is the backend's, read from each
 * assessment's own pages. A row opens that assessment; nothing here decides or runs anything. No score, no trend. */
function OttoProjectSection({ otto }: { otto: OttoProjectBlock }) {
  return (
    <Section title={otto.title} testId="project-otto">
      <p data-testid="project-otto-pack" className="break-words text-sm text-slate-300">
        {otto.pack_line}
      </p>
      <p data-testid="project-otto-note" className="mb-3 mt-1 break-words text-xs text-slate-400">
        {otto.note}
      </p>
      {otto.rows.length > 0 ? (
        <div className="rounded-xl border border-slate-800 text-sm">
          {otto.since_title ? (
            // The heading of the third column, on a screen wide enough to have columns.
            <div
              aria-hidden="true"
              className={`hidden gap-x-4 border-b border-slate-800 px-4 py-2 text-xs font-medium text-slate-400 md:grid ${OTTO_COLS}`}
            >
              <span />
              <span />
              <span>{otto.since_title}</span>
            </div>
          ) : null}
          <ul className="divide-y divide-slate-800">
            {otto.rows.map((row) => (
              <li
                key={row.assessment_id}
                data-testid="project-otto-row"
                data-assessment={row.assessment_id}
                data-waiting={row.waiting}
                className={`grid gap-x-4 gap-y-1 px-4 py-2.5 ${OTTO_COLS}`}
              >
                <a
                  href={routeHref(linkRoute(row.link, row.link.assessment_id ?? row.assessment_id))}
                  data-testid="project-otto-link"
                  className="min-w-0 break-words font-medium text-slate-100 hover:text-sky-300"
                >
                  {row.title}
                </a>
                <span data-testid="project-otto-waiting" className="min-w-0">
                  {row.waiting > 0 ? (
                    <StatusChip size="sm" label={row.waiting_text} tone="warn" wrap />
                  ) : (
                    <span className="text-slate-400">{row.waiting_text}</span>
                  )}
                </span>
                <div className="min-w-0">
                  {row.since.length > 0 ? (
                    <>
                      {otto.since_title ? (
                        <p className="text-xs font-medium text-slate-400 md:sr-only">{otto.since_title}</p>
                      ) : null}
                      <ul data-testid="project-otto-since" className="space-y-0.5 text-slate-300">
                        {row.since.map((line, i) => (
                          <li key={i} className="break-words">
                            {line}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Section>
  );
}

/** Phase 5b: the Project overview: every assessment of the project side by side, what changed between two, and which
 * of them share a system. Counts only, read from each assessment's own pages; no score, no trend. */
export function ProjectOverviewPage({
  projectId,
  workspace,
  onNewAssessment,
  onChanged,
}: {
  projectId: number;
  workspace: Workspace | null;
  onNewAssessment: () => void;
  onChanged: () => Promise<void> | void;
}) {
  const [view, setView] = useState<ProjectOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pick, setPick] = useState<{ from?: number; to?: number }>({});
  const [archived, setArchived] = useState(false);
  const [form, setForm] = useState<"rename" | "move" | null>(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const project = workspace?.projects.find((p) => p.id === projectId) ?? null;

  useEffect(() => {
    let live = true;
    api
      .getProjectOverview(projectId, { ...pick, archived })
      .then((v) => {
        if (live) {
          setView(v);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [projectId, pick, archived, tick, workspace]);

  async function act(call: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await call();
      setForm(null);
      await onChanged();
      setTick((n) => n + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<ProjectOverviewRow>[] = [
    {
      key: "assessment",
      header: "Assessment",
      minWidth: 180,
      render: (a) => (
        <>
          <a href={`#/a/${a.id}/overview`} className="font-medium text-slate-100 hover:text-sky-300">
            {a.title}
          </a>
          <span className="block text-xs text-slate-400">
            {[a.purpose?.label, a.reference, a.file?.filename ?? "No file yet"].filter(Boolean).join(" · ")}
          </span>
        </>
      ),
    },
    {
      key: "status",
      header: "Status",
      minWidth: 130,
      render: (a) => (
        <>
          <StatusChip size="sm" label={a.status.label} tone={a.status.key === "open" ? "pass" : "neutral"} />
          <span className="mt-1 block text-xs text-slate-400">
            {a.status.signoff
              ? `by ${a.status.signoff.by}, ${formatTime(a.status.signoff.at)}`
              : `since ${formatTime(a.created_at)}`}
          </span>
        </>
      ),
    },
    { key: "claims", header: "Claims", minWidth: 90, render: (a) => <ClaimsCell counts={a.headline} /> },
    { key: "tests", header: "Tests", minWidth: 90, render: (a) => <TestsCell counts={a.headline} /> },
    { key: "fixes", header: "Fixes", minWidth: 80, render: (a) => <FixesCell counts={a.headline} /> },
    { key: "systems", header: "Migration", minWidth: 110, render: (a) => <SystemsCell counts={a.headline} /> },
    {
      key: "blockers",
      header: "Blockers",
      minWidth: 80,
      render: (a) =>
        a.headline.blockers === null || a.headline.blockers === undefined ? (
          <span className="text-slate-500">Not yet</span>
        ) : (
          <span className="tabular-nums text-slate-200">{a.headline.blockers}</span>
        ),
    },
  ];

  const choices = view?.choices ?? [];
  return (
    <div data-testid="project-overview">
      <PageHeader
        eyebrow="Project overview"
        title={project?.name ?? "Project"}
        description={
          view
            ? `${view.rows.length} ${view.rows.length === 1 ? "assessment" : "assessments"}: ${view.rows.filter((r) => r.status.key === "open").length} open, ${view.rows.filter((r) => r.status.key === "closed").length} closed.`
            : undefined
        }
        actions={
          <>
            <SecondaryButton onClick={onNewAssessment}>New assessment</SecondaryButton>
            {project ? (
              <ActionsMenu
                label="More actions for this project"
                items={[
                  { label: "Rename", onClick: () => setForm("rename") },
                  { label: "Move to folder", onClick: () => setForm("move") },
                  project.archived
                    ? {
                        label: "Unarchive",
                        onClick: () => void act(() => api.changeProject(project.id, { archived: false })),
                      }
                    : {
                        label: "Archive",
                        onClick: () => void act(() => api.changeProject(project.id, { archived: true })),
                      },
                ]}
              />
            ) : null}
          </>
        }
      />
      {error ? (
        <div className="mb-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      {form === "rename" && project ? (
        <InlineForm
          title="Rename this project"
          submitLabel="Save name"
          initialName={project.name}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(name) => void act(() => api.changeProject(project.id, { name }))}
        />
      ) : form === "move" && project && workspace ? (
        <InlineForm
          title="Move this project to a folder"
          submitLabel="Move"
          nameLabel=""
          destination={{
            label: "Folder",
            options: folderOptions(workspace),
            initial: project.folder_id === null ? "" : String(project.folder_id),
          }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(_n, dest) =>
            void act(() => api.changeProject(project.id, { folder_id: dest ? Number(dest) : null, move: true }))
          }
        />
      ) : null}

      <Section
        title="Assessments"
        actions={
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
              className="h-4 w-4 accent-sky-500"
            />
            Show archived
          </label>
        }
      >
        {view ? (
          <DataTable
            label="Assessments in this project"
            columns={columns}
            rows={view.rows}
            rowKey={(a) => String(a.id)}
            rowTestId="assessment-row"
            onRowClick={(a) => {
              window.location.hash = `#/a/${a.id}/overview`;
            }}
          />
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </Section>

      {/* Phase 5c: proposals waiting in each assessment, and what changed since the newest test pack. */}
      {view?.otto ? <OttoProjectSection otto={view.otto} /> : null}

      <Section title="What changed">
        {view && choices.length >= 2 ? (
          <div data-testid="what-changed">
            <div className="mb-3 flex flex-wrap gap-3">
              <FilterSelect
                label="From"
                value={String(view.compare?.from_id ?? "")}
                options={choices.map((c) => ({ value: String(c.id), label: c.title }))}
                onChange={(v) => setPick((p) => ({ ...p, from: Number(v), to: p.to ?? view.compare?.to_id }))}
              />
              <FilterSelect
                label="To"
                value={String(view.compare?.to_id ?? "")}
                options={choices.map((c) => ({ value: String(c.id), label: c.title }))}
                onChange={(v) => setPick((p) => ({ ...p, to: Number(v), from: p.from ?? view.compare?.from_id }))}
              />
            </div>
            {view.compare ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {view.compare.lists.map((list) => (
                  <section
                    key={list.key}
                    data-testid="compare-list"
                    data-list={list.key}
                    className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm"
                  >
                    <h3 className="text-xs font-medium text-slate-400">{list.title}</h3>
                    <p className="mt-1 text-xl font-semibold tabular-nums text-slate-50">{list.items.length}</p>
                    <ul className="mt-2 space-y-1">
                      {list.items.map((item, i) => (
                        <li key={i}>
                          <a
                            href={routeHref(linkRoute(item.link, item.link.assessment_id ?? 0))}
                            className="text-sky-300 hover:underline"
                          >
                            {item.label}
                          </a>
                          <span className="block text-xs text-slate-400">{item.sub}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">Pick two assessments to compare.</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-slate-400">What changed shows once the project has two assessments.</p>
        )}
      </Section>

      <Section title="Shared systems">
        {view && view.shared.length > 0 ? (
          <ul
            data-testid="shared-systems"
            className="divide-y divide-slate-800 rounded-xl border border-slate-800 text-sm"
          >
            {view.shared.map((s) => (
              <li key={s.name} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-2.5">
                <span className="font-mono text-slate-100">{s.name}</span>
                <span className="text-slate-400">in {s.assessments.map((a) => a.title).join(", ")}</span>
                {s.note ? <span className="text-amber-200/90">{s.note}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">No system is named by more than one assessment of this project.</p>
        )}
      </Section>
    </div>
  );
}
