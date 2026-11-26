import { useState } from "react";
import {
  api,
  errorMessage,
  type AssessmentView,
  type OttoWaiting,
  type OverviewFact,
  type OverviewGroup,
  type SourceCount,
  type Workspace,
} from "../../api";
import type { Page } from "../../router";
import { PageHeader } from "../layout";
import { ItemLinkView } from "../related";
import { DemoDataLabel, ErrorBox, PrimaryButton, SecondaryButton, StatusChip, WhereFromTag, formatTime } from "../ui";
import { ActionsMenu, InlineForm, Section } from "./parts";

function Facts({ facts }: { facts: OverviewFact[] }) {
  return (
    <ul className="space-y-1">
      {facts.map((f) => (
        <li key={f.label}>
          <ItemLinkView link={f.link} testId="overview-fact" className="text-sky-300 hover:underline">
            {f.label} <span className="tabular-nums">{f.value}</span>
          </ItemLinkView>
        </li>
      ))}
    </ul>
  );
}

function Counts({
  label,
  counts,
  link,
}: {
  label: string;
  counts: { open: number; in_progress: number; done: number };
  link: { page: string; group: string };
}) {
  return (
    <p className="text-xs text-slate-400">
      <ItemLinkView
        link={{ page: link.page, item: null, group: link.group }}
        className="hover:text-slate-200 hover:underline"
      >
        {label}: Open {counts.open} · In progress {counts.in_progress} · Done {counts.done}
      </ItemLinkView>
    </p>
  );
}

/** Where it came from (22 November 2026): how many of the group's checks rest on each source, in the backend's order and
 * words (a source with none is left out). It counts what the checks say and decides nothing. */
function SourceCounts({ counts }: { counts: SourceCount[] }) {
  return (
    <p
      data-testid="overview-source-counts"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400"
    >
      {/* the spaces are for a screen reader and a copy: a flex box draws only the gaps */}
      <span>Where these came from:</span>{" "}
      {counts.map((c, i) => (
        <span
          key={c.key}
          data-testid="overview-source-count"
          data-source={c.key}
          className="inline-flex items-center gap-1"
        >
          <span className="tabular-nums text-slate-300">{c.count}</span>{" "}
          <WhereFromTag
            tag={{ key: c.key, label: c.label, meaning: c.meaning, note: null }}
            testId="overview-source-tag"
          />
          {/* the dot ends an item, so a wrapped line starts with its number */}
          {i < counts.length - 1 ? <span aria-hidden="true"> ·</span> : null}{" "}
        </span>
      ))}
    </p>
  );
}

/** One work group of the assessment on the Overview: its checks and fixes counts and its facts, each a link. */
function GroupBlock({ group }: { group: OverviewGroup }) {
  return (
    <section
      data-testid="overview-group"
      data-group={group.key}
      aria-label={group.label}
      className="rounded-xl border border-slate-800 bg-slate-900/40"
    >
      <h2 className="rounded-t-xl border-b border-slate-800 bg-slate-900/80 px-4 py-2 text-sm font-semibold text-slate-100">
        {group.label}
      </h2>
      <div className="space-y-2 px-4 py-3 text-sm">
        {group.checks ? (
          <Counts label="Checks" counts={group.checks} link={{ page: "checks", group: group.key }} />
        ) : null}
        {group.source_counts && group.source_counts.length > 0 ? <SourceCounts counts={group.source_counts} /> : null}
        {group.facts.length > 0 ? <Facts facts={group.facts} /> : null}
        {group.fixes ? <Counts label="Fixes" counts={group.fixes} link={{ page: "fixes", group: group.key }} /> : null}
        {group.empty_text ? <p className="text-slate-400">{group.empty_text}</p> : null}
      </div>
    </section>
  );
}

/** Phase 5c: "Waiting for you". How many of Otto's proposals nobody has decided yet, each kind a link to the page it
 * lives on. Every word and count is the backend's; the block opens pages and decides nothing. With nothing waiting it
 * keeps its one calm line and shows no link. */
function WaitingBlock({ waiting }: { waiting: OttoWaiting }) {
  const some = waiting.total > 0;
  return (
    <section
      aria-label={waiting.title}
      data-testid="overview-waiting"
      data-total={waiting.total}
      className={`mb-4 rounded-xl border bg-slate-900/50 p-5 text-sm ${some ? "border-slate-600" : "border-slate-800"}`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{waiting.title}</p>
      <p data-testid="waiting-line" className={`mt-1.5 break-words ${some ? "text-slate-100" : "text-slate-400"}`}>
        {waiting.line}
      </p>
      {some && waiting.items.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
          {waiting.items.map((item) => (
            <li key={item.kind} data-testid="waiting-item" data-kind={item.kind} data-count={item.count}>
              <ItemLinkView link={item.link} testId="waiting-link">
                {item.text}
              </ItemLinkView>
            </li>
          ))}
        </ul>
      ) : null}
      <p data-testid="waiting-note" className="mt-2 break-words text-xs text-slate-400">
        {waiting.note}
      </p>
    </section>
  );
}

/** Phase 5b: the whole assessment on one page. Every number is read from the page it links to; no score. */
export function OverviewPage({
  assessment,
  workspace,
  guided,
  onGuided,
  onGo,
  onChanged,
  onNewAssessment,
  onRerun,
  onClose,
}: {
  assessment: AssessmentView;
  workspace: Workspace | null;
  guided: boolean;
  onGuided: (on: boolean) => void;
  onGo: (page: Page) => void;
  onOpenAssessment: (id: number) => void;
  onChanged: () => Promise<void> | void;
  onNewAssessment: () => void;
  onRerun: () => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<"rename" | "move" | "purpose" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closed = assessment.status.key === "closed";

  async function act(call: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await call();
      setForm(null);
      await onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const projectOptions = (workspace?.projects ?? [])
    .filter((p) => !p.archived)
    .map((p) => ({ value: String(p.id), label: [...p.path.map((s) => s.name), p.name].join(" / ") }));
  const purposeOptions = (workspace?.purposes ?? []).map((p) => ({ value: p.key, label: p.label }));
  const blocks = assessment.blocks ?? null;
  const signoff = assessment.status.signoff;

  return (
    <div data-testid="overview-page">
      <PageHeader
        eyebrow={assessment.project.name}
        title={assessment.title}
        description={
          <span className="flex flex-col gap-1.5">
            <span className="flex flex-wrap items-center gap-2">
              {assessment.purpose ? (
                <StatusChip size="sm" label={assessment.purpose.label} tone="neutral" testId="assessment-purpose" />
              ) : null}
              {assessment.reference ? <span className="text-slate-300">{assessment.reference}</span> : null}
              <StatusChip size="sm" label={assessment.status.label} tone={closed ? "neutral" : "pass"} />
              <span>Started {formatTime(assessment.created_at)}</span>
              {signoff ? (
                <span data-testid="signoff-line">
                  · Signed off by {signoff.by}, {formatTime(signoff.at)}
                </span>
              ) : null}
            </span>
            {assessment.file ? (
              <span className="flex flex-wrap items-center gap-2">
                <span>
                  <span className="font-mono text-slate-300">{assessment.file.filename}</span>, imported{" "}
                  {formatTime(assessment.file.imported_at)}
                </span>
                {assessment.file.is_demo ? <DemoDataLabel /> : null}
              </span>
            ) : (
              <span>No scanner file in this assessment yet.</span>
            )}
          </span>
        }
        actions={
          <>
            <SecondaryButton allowWhenClosed onClick={onNewAssessment}>
              New assessment
            </SecondaryButton>
            {!closed ? <SecondaryButton onClick={onClose}>Close assessment</SecondaryButton> : null}
            {assessment.file ? (
              <SecondaryButton allowWhenClosed onClick={onRerun}>
                Rerun as new assessment
              </SecondaryButton>
            ) : null}
            <ActionsMenu
              label="More actions for this assessment"
              items={[
                { label: "Rename", onClick: () => setForm("rename") },
                ...(!closed ? [{ label: "Change purpose", onClick: () => setForm("purpose") }] : []),
                { label: "Move to another project", onClick: () => setForm("move") },
                assessment.archived
                  ? {
                      label: "Unarchive",
                      onClick: () => void act(() => api.changeAssessment(assessment.id, { archived: false })),
                    }
                  : {
                      label: "Archive",
                      onClick: () => void act(() => api.changeAssessment(assessment.id, { archived: true })),
                    },
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
      ) : form === "purpose" ? (
        <InlineForm
          title="Change purpose"
          submitLabel="Save purpose"
          nameLabel="Reference (optional)"
          initialName={assessment.reference ?? ""}
          destination={{ label: "Purpose", options: purposeOptions, initial: assessment.purpose?.key ?? "full_review" }}
          busy={busy}
          error={error}
          onCancel={() => setForm(null)}
          onSubmit={(reference, purpose) => void act(() => api.changeAssessment(assessment.id, { purpose, reference }))}
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

      {/* Phase 5c: Otto's proposals that wait for a decision come first; an answer from before they existed has none. */}
      {assessment.waiting ? <WaitingBlock waiting={assessment.waiting} /> : null}

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <section
          aria-label="Next step"
          data-testid="next-step"
          className="rounded-xl border border-slate-800 bg-slate-900/50 p-5"
        >
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Next step</p>
          <p className="mt-1.5 text-sm text-slate-300">{assessment.next_step.text}</p>
          <div className="mt-4">
            {assessment.next_step.page === "overview" ? (
              <PrimaryButton allowWhenClosed onClick={onNewAssessment}>
                {assessment.next_step.label}
              </PrimaryButton>
            ) : (
              <PrimaryButton allowWhenClosed onClick={() => onGo(assessment.next_step.page as Page)}>
                {assessment.next_step.label}
              </PrimaryButton>
            )}
          </div>
        </section>
        <section
          aria-label="Brought in"
          data-testid="brought-in"
          className="rounded-xl border border-slate-800 bg-slate-900/50 p-5 text-sm"
        >
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Brought in</p>
          {assessment.import ? (
            <div className="mt-1.5 space-y-1 text-slate-300">
              <p>
                <ItemLinkView link={{ page: "inventory/import", item: null }}>
                  <span className="font-mono">{assessment.import.filename}</span>
                </ItemLinkView>
                : {assessment.import.claims.length} {assessment.import.claims.length === 1 ? "claim" : "claims"},{" "}
                {assessment.import.addresses.length} {assessment.import.addresses.length === 1 ? "server" : "servers"}{" "}
                named
              </p>
              <p className="text-slate-400">
                <ItemLinkView link={{ page: "migration/dependencies", item: null }}>Dependency list</ItemLinkView>:{" "}
                {blocks?.groups.find((g) => g.key === "dependencies")?.facts.length ? "added" : "none yet"}
              </p>
              {/* The design refactor (26 November 2026): the systems these files describe, drawn as a map. */}
              <p className="text-slate-400">
                <ItemLinkView link={{ page: "observatory", item: null }} testId="overview-map-link">
                  See your systems on the map
                </ItemLinkView>
                : where the cryptography is, and what each check found there
              </p>
            </div>
          ) : (
            <p className="mt-1.5 text-slate-400">
              Nothing yet. Bring in the file your scanner made, or use the demo file.
            </p>
          )}
        </section>
      </div>

      {blocks ? (
        <>
          <div data-testid="overview-groups" className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {blocks.groups.map((g) => (
              <GroupBlock key={g.key} group={g} />
            ))}
          </div>
          <div className="mb-6 grid gap-4 lg:grid-cols-2">
            <section
              aria-label="Open findings"
              data-testid="open-findings"
              className="rounded-xl border border-slate-800 bg-slate-900/50 p-5 text-sm"
            >
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Open findings</p>
              <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
                {blocks.findings.map((f) => (
                  <li key={f.label}>
                    <ItemLinkView link={f.link} testId="finding-count">
                      {f.label} <span className="tabular-nums">{f.value}</span>
                    </ItemLinkView>
                  </li>
                ))}
              </ul>
              {blocks.watch_list ? (
                // Sandbox research (prototype): information, never a finding or a result. It opens the Watch list.
                <p
                  data-testid="overview-watch-list"
                  className="mt-3 break-words border-t border-slate-800 pt-3 text-slate-300"
                >
                  {blocks.watch_list.line}{" "}
                  <ItemLinkView
                    link={blocks.watch_list.link}
                    testId="overview-watch-list-link"
                    className="text-sky-300 underline-offset-2 hover:underline"
                  >
                    Open the Watch list
                  </ItemLinkView>
                </p>
              ) : null}
            </section>
            <section
              aria-label="Evidence"
              data-testid="overview-evidence"
              className="rounded-xl border border-slate-800 bg-slate-900/50 p-5 text-sm"
            >
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Evidence</p>
              <p className="mt-2 text-slate-300">
                <ItemLinkView link={{ page: "evidence", item: null }}>
                  {blocks.evidence.runs} {blocks.evidence.runs === 1 ? "run" : "runs"} recorded
                </ItemLinkView>
                .{" "}
                {blocks.evidence.last_download ? (
                  <span>
                    Last download {formatTime(blocks.evidence.last_download.at)}, fingerprint{" "}
                    <span className="font-mono" title={blocks.evidence.last_download.fingerprint}>
                      {blocks.evidence.last_download.fingerprint.slice(0, 12)}
                    </span>
                    .
                  </span>
                ) : (
                  "Not downloaded yet."
                )}
              </p>
            </section>
          </div>
        </>
      ) : null}

      <Section title="Guided demo">
        <label className="flex items-start justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <span>
            <span className="block text-sm font-medium text-slate-100">Guided demo</span>
            <span className="mt-1 block text-xs leading-relaxed text-slate-400">
              Walks the pages in today&apos;s order, with Back and Next at the bottom of each: Import, Verify, Checks,
              Evidence, Fixes, Migration.
            </span>
          </span>
          <input
            type="checkbox"
            role="switch"
            aria-checked={guided}
            aria-label="Guided demo"
            checked={guided}
            onChange={(e) => onGuided(e.target.checked)}
            className="mt-1 h-4 w-4 accent-sky-500"
          />
        </label>
      </Section>

      <p className="text-sm text-slate-400">
        Every assessment of this project, side by side:{" "}
        <a
          href={`#/p/${assessment.project.id}`}
          data-testid="to-project-overview"
          className="text-sky-300 hover:underline"
        >
          Project overview
        </a>
        .
      </p>
    </div>
  );
}
