import { useEffect, useState } from "react";
import { api, errorMessage, type AssessmentView, type ProjectView, type Workspace } from "../../api";
import type { Page } from "../../router";
import { DataTable, PageHeader, SummaryCards, type Column } from "../layout";
import { DemoDataLabel, ErrorBox, PrimaryButton, SecondaryButton, StatusChip, formatTime } from "../ui";
import { ActionsMenu, InlineForm, SYSTEM_STATUS_WORDS, Section } from "./parts";

type AssessmentRowData = ProjectView["assessments"][number];

/** The Overview of one assessment: its real counts, what was imported and when, the next step, its history. */
export function OverviewPage({
  assessment,
  workspace,
  guided,
  onGuided,
  onGo,
  onOpenAssessment,
  onChanged,
}: {
  assessment: AssessmentView;
  workspace: Workspace | null;
  guided: boolean;
  onGuided: (on: boolean) => void;
  onGo: (page: Page) => void;
  onOpenAssessment: (id: number) => void;
  onChanged: () => Promise<void> | void;
}) {
  const [project, setProject] = useState<ProjectView | null>(null);
  const [form, setForm] = useState<"rename" | "move" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closed = assessment.status.key === "closed";

  useEffect(() => {
    let live = true;
    api
      .getProject(assessment.project.id)
      .then((p) => live && setProject(p))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [assessment.project.id, assessment.id, assessment.status.key, assessment.title]);

  async function act(call: () => Promise<unknown>, after?: (r: unknown) => void) {
    setBusy(true);
    setError(null);
    try {
      const r = await call();
      setForm(null);
      await onChanged();
      after?.(r);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const c = assessment.counts;
  const cards = [
    {
      key: "claims",
      label: "Claims checked",
      value: c.claims ? c.claims.checked : "—",
      sub: c.claims ? `${c.claims.false} false · ${c.claims.true} true · ${c.claims.couldnt_check} couldn't check` : "Not verified yet",
    },
    {
      key: "tests",
      label: "Tests failed",
      value: c.tests ? c.tests.failed : "—",
      sub: c.tests ? `of ${c.tests.run} run · ${c.tests.passed} passed` : "No test has run yet",
    },
    {
      key: "fixes",
      label: "Open fixes",
      value: c.fixes ? c.fixes.open : "—",
      sub: c.fixes ? `of ${c.fixes.total} in Fixes` : "Nothing in Fixes yet",
    },
    {
      key: "systems",
      label: "Systems measured",
      value: c.systems ? c.systems.total - c.systems.not_measured : "—",
      sub: c.systems
        ? SYSTEM_STATUS_WORDS.filter((w) => c.systems && c.systems[w.key] > 0)
            .map((w) => `${c.systems?.[w.key]} ${w.label.toLowerCase()}`)
            .join(" · ")
        : "Migration has not measured yet",
    },
  ];

  const history: Column<AssessmentRowData>[] = [
    {
      key: "title",
      header: "Assessment",
      render: (a) => (
        <span className="flex items-center gap-2 font-medium text-slate-100">
          {a.title}
          {a.id === assessment.id ? <span className="text-xs font-normal text-slate-500">(this one)</span> : null}
        </span>
      ),
    },
    { key: "file", header: "File", render: (a) => <span className="text-slate-300">{a.file ? a.file.filename : "No file yet"}</span> },
    { key: "status", header: "Status", render: (a) => <StatusChip size="sm" label={a.status.label} tone={a.status.key === "open" ? "pass" : "neutral"} /> },
    { key: "opened", header: "Started", render: (a) => <span className="text-slate-400">{formatTime(a.created_at)}</span> },
  ];

  const projectOptions = (workspace?.projects ?? [])
    .filter((p) => !p.archived)
    .map((p) => ({ value: String(p.id), label: [...p.path.map((s) => s.name), p.name].join(" / ") }));

  return (
    <div data-testid="overview-page">
      <PageHeader
        eyebrow={assessment.project.name}
        title={assessment.title}
        description={
          assessment.file ? (
            <span className="flex flex-wrap items-center gap-2">
              <span>
                <span className="font-mono text-slate-300">{assessment.file.filename}</span>, imported {formatTime(assessment.file.imported_at)}
              </span>
              {assessment.file.is_demo ? <DemoDataLabel /> : null}
            </span>
          ) : (
            "No scanner file in this assessment yet."
          )
        }
        actions={
          <>
            <SecondaryButton
              allowWhenClosed
              onClick={() => void act(() => api.newAssessment(assessment.project.id), (r) => onOpenAssessment((r as { id: number }).id))}
            >
              New assessment
            </SecondaryButton>
            {!closed ? (
              <SecondaryButton onClick={() => void act(() => api.changeAssessment(assessment.id, { close: true }))}>Close assessment</SecondaryButton>
            ) : null}
            <ActionsMenu
              label="More actions for this assessment"
              items={[
                { label: "Rename", onClick: () => setForm("rename") },
                { label: "Move to another project", onClick: () => setForm("move") },
                assessment.archived
                  ? { label: "Unarchive", onClick: () => void act(() => api.changeAssessment(assessment.id, { archived: false })) }
                  : { label: "Archive", onClick: () => void act(() => api.changeAssessment(assessment.id, { archived: true })) },
              ]}
            />
          </>
        }
      />
      {error && !form ? (
        <div className="mb-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      {form === "rename" ? (
        <InlineForm
          title="Rename this assessment"
          submitLabel="Save name"
          initialName={assessment.title}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(name) => void act(() => api.changeAssessment(assessment.id, { name }))}
        />
      ) : form === "move" ? (
        <InlineForm
          title="Move this assessment to another project"
          submitLabel="Move"
          nameLabel=""
          destination={{ label: "Project", options: projectOptions, initial: String(assessment.project.id) }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(_n, dest) => void act(() => api.changeAssessment(assessment.id, { project_id: Number(dest) }))}
        />
      ) : null}

      <SummaryCards label="This assessment in numbers" cards={cards} />

      <div className="mb-6 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section aria-label="Next step" data-testid="next-step" className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Next step</p>
          <p className="mt-1.5 text-sm text-slate-300">{assessment.next_step.text}</p>
          <div className="mt-4">
            {assessment.next_step.page === "overview" ? (
              <PrimaryButton
                allowWhenClosed
                onClick={() => void act(() => api.newAssessment(assessment.project.id), (r) => onOpenAssessment((r as { id: number }).id))}
              >
                {assessment.next_step.label}
              </PrimaryButton>
            ) : (
              <PrimaryButton allowWhenClosed onClick={() => onGo(assessment.next_step.page as Page)}>
                {assessment.next_step.label}
              </PrimaryButton>
            )}
          </div>
        </section>
        <section aria-label="Guided demo" className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <label className="flex items-start justify-between gap-4">
            <span>
              <span className="block text-sm font-medium text-slate-100">Guided demo</span>
              <span className="mt-1 block text-xs leading-relaxed text-slate-400">
                Walks the pages in today's order, with Back and Next at the bottom of each: Import, Verify, Tests, Evidence, Fixes,
                Migration.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              aria-checked={guided}
              checked={guided}
              onChange={(e) => onGuided(e.target.checked)}
              className="mt-1 h-4 w-4 accent-sky-500"
            />
          </label>
        </section>
      </div>

      {assessment.import ? (
        <Section title="What was imported">
          <dl className="grid gap-x-6 gap-y-2 rounded-xl border border-slate-800 bg-slate-900/30 p-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-slate-500">File</dt>
              <dd className="font-mono text-slate-200">{assessment.import.filename}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Claims in the file</dt>
              <dd className="text-slate-200">{assessment.import.claims.length}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Servers named</dt>
              <dd className="text-slate-200">{assessment.import.addresses.length}</dd>
            </div>
          </dl>
        </Section>
      ) : null}

      <Section title="History of this project">
        {project ? (
          <DataTable
            label="Assessments in this project"
            columns={history}
            rows={project.assessments.filter((a) => !a.archived || a.id === assessment.id)}
            rowKey={(a) => String(a.id)}
            rowTestId="history-row"
            selectedKey={String(assessment.id)}
            onRowClick={(a) => a.id !== assessment.id && onOpenAssessment(a.id)}
          />
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </Section>
    </div>
  );
}
