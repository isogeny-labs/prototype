import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  errorMessage,
  type EvidenceExport,
  type LabResult,
  type LabRow,
  type LabView,
  type RichText,
  type RowStatus,
} from "../api";
import { DownloadStatus, downloadEvidence } from "./evidenceDownload";
import { DataTable, DetailPanel, FilterSelect, PageHeader, SearchInput, SummaryCards, TableWithPanel, Toolbar, type Column } from "./layout";
import { ResultDetail } from "./lab/ResultDetail";
import {
  AlsoNoticedList,
  DemoDataLabel,
  ErrorBox,
  NotTestedBox,
  ResultBadge,
  RichTextView,
  SecondaryButton,
  SourceTag,
  StatusChip,
  StatusView,
  splitByGroup,
  useDismiss,
} from "./ui";

const POLL_MS = 1000;

function unfinished(status: RowStatus | null): boolean {
  return status !== null && (status.status === "waiting" || status.status === "running");
}

/** A proof is running in Fixes for this result's fix: its line says so until the proof ends. */
function proving(result: LabResult | null): boolean {
  return result?.fix_line?.busy === true;
}

/**
 * Ask again while the answer says something is running. `busy` alone covers every case, also a proof whose line
 * no row shows (the tests it is for are no longer in the plan); the other checks are kept as a second net.
 */
function needsPolling(lab: LabView): boolean {
  return (
    lab.busy ||
    lab.retest.running ||
    lab.rows.some(
      (row) => unfinished(row.result_status) || unfinished(row.after_status) || proving(row.result) || proving(row.after),
    )
  );
}

/** A before or after column heading, with a second line saying which code that side ran on. */
function ColumnHeading({ heading, note }: { heading: string; note: RichText }) {
  return (
    <span>
      {heading}
      {note.length > 0 ? (
        <span data-testid="lab-column-note" className="mt-0.5 block normal-case tracking-normal text-slate-400">
          <RichTextView parts={note} />
        </span>
      ) : null}
    </span>
  );
}

/** One side of a before/after row: the badge and one short line, or the live status. */
function Cell({
  result,
  status,
  testId,
}: {
  result: LabResult | null;
  status: RowStatus | null;
  testId: string;
}) {
  return (
    <div data-testid={testId} className="min-w-0">
      {result ? (
        <>
          <ResultBadge label={result.label} tone={result.tone} />
          <p className="mt-1.5 text-[13px] leading-snug text-slate-300">{result.plain}</p>
        </>
      ) : status ? (
        <StatusView status={status} />
      ) : null}
    </div>
  );
}

/** The first column: the test's name, its control line, and any "Also noticed" side note. */
function TestCell({ row, beforeAfter }: { row: LabRow; beforeAfter: boolean }) {
  const noticed = leading(row, beforeAfter);
  return (
    <div className="min-w-0" data-kind={row.kind}>
      <div data-testid="lab-row-header">
        <p className="text-[15px] font-medium text-slate-100">{row.title}</p>
        {row.control_line ? <p className="mt-1 text-xs text-slate-400">{row.control_line}</p> : null}
      </div>
      {noticed && noticed.also_noticed.length > 0 ? (
        <div className="mt-2">
          <AlsoNoticedList title={noticed.also_noticed_title} items={noticed.also_noticed} />
        </div>
      ) : null}
    </div>
  );
}

/** The result a row leads with: the newest one in the before/after view. */
function leading(row: LabRow, beforeAfter: boolean): LabResult | null {
  return beforeAfter ? (row.after ?? row.result) : row.result;
}

type StatusFilter = "all" | "none" | LabResult["code"];

const CODE_NAMES: Partial<Record<LabResult["code"], string>> = {
  passed: "Passed",
  failed: "Failed",
  couldnt_run: "Couldn't run",
  couldnt_trust: "Couldn't trust this run",
  measured: "Measured",
};

interface Props {
  planId: number;
  /** "View in Fixes" on a failed result: the app opens the Fixes step on that fix. */
  onViewFix: (fixId: string) => void;
}

export function EvidenceLabScreen({ planId, onViewFix }: Props) {
  const [lab, setLab] = useState<LabView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [menuOpen, setMenuOpen] = useState(false);
  const [exported, setExported] = useState<EvidenceExport | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useDismiss(menuOpen, menuRef, closeMenu);
  const closePanel = useCallback(() => setOpenRow(null), []);

  useEffect(() => {
    let live = true;
    api
      .getLab(planId)
      .then((next) => {
        if (live) setLab(next);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId]);

  // While a retest (or any test, or a proof in Fixes) is still going, ask again every second.
  const polling = lab !== null && needsPolling(lab);
  useEffect(() => {
    if (!polling) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .getLab(planId)
        .then((next) => {
          if (!live) return;
          setLab(next);
          setPollTick((n) => n + 1);
        })
        .catch((e: unknown) => {
          if (!live) return;
          setError(errorMessage(e));
          setPollTick((n) => n + 1);
        });
    }, POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [planId, polling, pollTick]);

  if (!lab) {
    return (
      <section aria-labelledby="lab-title" className="space-y-4">
        <h1 id="lab-title" className="text-2xl font-semibold tracking-tight text-slate-50">
          Evidence
        </h1>
        {error ? (
          <ErrorBox title="The results couldn't be loaded">{error}</ErrorBox>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </section>
    );
  }

  const current = lab;

  async function act(call: () => Promise<LabView>) {
    setBusy(true);
    setError(null);
    try {
      setLab(await call());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    setBusy(true);
    setError(null);
    try {
      setExported(await downloadEvidence(current.plan_id));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const beforeAfter = current.view === "before_after";
  const headings = new Map(current.groups.map((g) => [g.key, g]));

  // Summary cards: counts of rows by their badge code, nothing else.
  const codes = current.rows.map((r) => leading(r, beforeAfter)?.code ?? null);
  const count = (...which: LabResult["code"][]) => codes.filter((c) => c !== null && which.includes(c)).length;
  const cards = [
    { key: "with-result", label: "Tests with a result", value: codes.filter((c) => c !== null).length, sub: `of ${current.rows.length} in the plan` },
    { key: "failed", label: "Failed", value: count("failed") },
    { key: "passed", label: "Passed", value: count("passed") },
    { key: "couldnt-run", label: "Couldn't run", value: count("couldnt_run", "couldnt_trust") },
  ];

  const present = Array.from(new Set(codes.filter((c): c is LabResult["code"] => c !== null)));
  const labelOfCode = (code: LabResult["code"]) =>
    CODE_NAMES[code] ??
    current.rows.map((r) => leading(r, beforeAfter)).find((r) => r?.code === code)?.label ??
    code;
  const statusOptions: { value: StatusFilter; label: string }[] = [
    { value: "all", label: "All results" },
    ...present.map((code) => ({ value: code as StatusFilter, label: labelOfCode(code) })),
    ...(codes.includes(null) ? [{ value: "none" as StatusFilter, label: "No result yet" }] : []),
  ];

  const needle = search.trim().toLowerCase();
  const visible = current.rows.filter((row) => {
    const result = leading(row, beforeAfter);
    if (statusFilter === "none" ? result !== null : statusFilter !== "all" && result?.code !== statusFilter) return false;
    if (!needle) return true;
    const group = row.group !== null ? headings.get(row.group)?.heading : "";
    return [row.title, row.control_line, result?.plain, group].some((t) => (t ?? "").toLowerCase().includes(needle));
  });

  const selected = current.rows.find((r) => r.item_id === openRow && (r.result !== null || r.after !== null)) ?? null;

  const retest = current.retest;
  const blocked = [
    !retest.can_start && !retest.running ? retest.blocked_reason : null,
    !current.download.can_start ? current.download.blocked_reason : null,
  ].filter((reason, i, all): reason is string => Boolean(reason) && all.indexOf(reason) === i);

  const columns: Column<LabRow>[] =
    beforeAfter && current.columns
      ? [
          {
            key: "test",
            header: current.columns.test,
            render: (row) => <TestCell row={row} beforeAfter />,
          },
          {
            key: "before",
            header: <ColumnHeading heading={current.columns.before} note={current.columns.before_note} />,
            render: (row) => <Cell result={row.result} status={row.result_status} testId="lab-cell-before" />,
          },
          {
            key: "after",
            header: <ColumnHeading heading={current.columns.after} note={current.columns.after_note} />,
            render: (row) => <Cell result={row.after} status={row.after_status} testId="lab-cell-after" />,
          },
        ]
      : [
          { key: "test", header: "Test", render: (row) => <TestCell row={row} beforeAfter={false} /> },
          {
            key: "result",
            header: "Result",
            render: (row) =>
              row.result ? (
                <div className="min-w-0">
                  <ResultBadge label={row.result.label} tone={row.result.tone} />
                  <p className="mt-1.5 text-[13px] leading-snug text-slate-300">{row.result.plain}</p>
                </div>
              ) : row.result_status ? (
                <StatusView status={row.result_status} />
              ) : null,
          },
        ];

  const table = (rows: LabRow[], first: boolean, label: string) => (
    <DataTable
      label={label}
      columns={columns}
      rows={rows}
      rowKey={(r) => String(r.item_id)}
      rowTestId="evidence-row"
      headTestId={first && beforeAfter ? "lab-columns" : undefined}
      selectedKey={selected ? String(selected.item_id) : null}
      onRowClick={(r) => {
        if (r.result === null && r.after === null) return;
        setOpenRow((cur) => (cur === r.item_id ? null : r.item_id));
      }}
    />
  );

  const listing =
    current.rows.length === 0 ? (
      <p className="text-sm text-slate-400">There are no results yet.</p>
    ) : visible.length === 0 ? (
      <p className="rounded-xl border border-slate-800 px-4 py-8 text-center text-sm text-slate-400">No results match this search.</p>
    ) : current.grouped ? (
      <div className="flex flex-col gap-6">
        {splitByGroup(current.groups, visible, (r) => r.group).map((section, i) => {
          const group = section.key !== null ? headings.get(section.key) : undefined;
          return (
            <section key={section.key ?? `rest-${i}`} data-testid="lab-group" data-group={section.key ?? ""}>
              {group ? (
                <>
                  <h2 className="text-base font-semibold text-slate-100">{group.heading}</h2>
                  {group.note ? (
                    <p data-testid="lab-group-note" className="mt-0.5 text-[13px] text-slate-400">
                      {group.note}
                    </p>
                  ) : null}
                </>
              ) : null}
              <div className="mt-3">{table(section.items, i === 0, group?.heading ?? "Results")}</div>
            </section>
          );
        })}
      </div>
    ) : (
      table(visible, true, "Results")
    );

  const panel = (
    <DetailPanel
      open={selected !== null}
      title={selected?.title ?? ""}
      subtitle={
        selected ? (
          <span className="flex flex-wrap items-center gap-2">
            {leading(selected, beforeAfter) ? (
              <StatusChip label={leading(selected, beforeAfter)!.label} tone={leading(selected, beforeAfter)!.tone} size="sm" />
            ) : null}
            {selected.control_line ? <span>{selected.control_line}</span> : null}
          </span>
        ) : null
      }
      onClose={closePanel}
    >
      {selected ? (
        <div data-testid="lab-row" data-kind={selected.kind} id={`lab-detail-${selected.item_id}`}>
          {beforeAfter ? (
            <>
              {selected.after ? (
                <ResultDetail
                  result={selected.after}
                  heading={current.columns?.after_heading}
                  busy={busy}
                  onMarkReviewed={(runId) => void act(() => api.markReviewed(runId))}
                  onDigDeeper={(runId) => void act(() => api.digDeeper(runId))}
                  onViewFix={onViewFix}
                />
              ) : null}
              {selected.result ? (
                <ResultDetail
                  result={selected.result}
                  heading={current.columns?.before_heading}
                  busy={busy}
                  onMarkReviewed={(runId) => void act(() => api.markReviewed(runId))}
                  onDigDeeper={(runId) => void act(() => api.digDeeper(runId))}
                  onViewFix={onViewFix}
                />
              ) : null}
            </>
          ) : selected.result ? (
            <ResultDetail
              result={selected.result}
              busy={busy}
              onMarkReviewed={(runId) => void act(() => api.markReviewed(runId))}
              onDigDeeper={(runId) => void act(() => api.digDeeper(runId))}
              onViewFix={onViewFix}
            />
          ) : null}
        </div>
      ) : null}
    </DetailPanel>
  );

  return (
    <section aria-label="Evidence">
      <PageHeader
        eyebrow={current.is_demo ? <DemoDataLabel /> : undefined}
        title="Evidence"
        description={
          <>
            <p data-testid="lab-subline">
              <RichTextView parts={current.subline} />
            </p>
            {current.code_line ? (
              <p data-testid="lab-code-line" className="mt-1 text-slate-300">
                <RichTextView parts={current.code_line} />
              </p>
            ) : null}
          </>
        }
        actions={
          <div ref={menuRef} className="relative flex shrink-0 flex-wrap gap-2.5">
            <SecondaryButton expanded={menuOpen} disabled={busy || !retest.can_start} onClick={() => setMenuOpen((v) => !v)}>
              Retest new version
            </SecondaryButton>
            <SecondaryButton allowWhenClosed disabled={busy || !current.download.can_start} onClick={() => void download()}>
              Download evidence
            </SecondaryButton>
            {menuOpen ? (
              <div
                role="menu"
                aria-label={retest.menu_title}
                className="absolute right-0 top-[46px] z-20 w-[420px] max-w-[calc(100vw-2rem)] rounded-[10px] border border-slate-600 bg-slate-900 p-1.5 shadow-2xl shadow-black/60"
              >
                <p className="px-2.5 pb-1.5 pt-2 text-xs text-slate-400">{retest.menu_title}</p>
                {retest.versions.map((v) => (
                  <button
                    key={`${v.component ?? ""}/${v.version}`}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      setExported(null);
                      void act(() => api.retest(current.plan_id, v.version, v.component));
                    }}
                    className="block w-full rounded-md p-2.5 text-left hover:bg-slate-800 focus-visible:bg-slate-800"
                  >
                    <span className="text-sm font-semibold text-slate-100">{v.label}</span>
                    {v.tag ? (
                      <>
                        {" "}
                        <SourceTag>{v.tag}</SourceTag>
                      </>
                    ) : null}
                    <span className="mt-0.5 block text-[13px] text-slate-400">{v.note}</span>
                  </button>
                ))}
                <p className="mt-1.5 border-t border-slate-800 px-2.5 pb-1 pt-2 text-xs text-slate-400">{retest.menu_note}</p>
              </div>
            ) : null}
          </div>
        }
      />

      <SummaryCards label="Evidence summary" cards={cards} />

      {retest.running && retest.progress_text ? (
        <p role="status" data-testid="retest-progress" className="mb-3 text-sm text-slate-300">
          {retest.progress_text}
        </p>
      ) : null}

      {blocked.map((reason) => (
        <p key={reason} data-testid="blocked-reason" className="mb-3 text-xs text-slate-400">
          {reason}
        </p>
      ))}

      {exported ? <DownloadStatus exported={exported} /> : null}

      {current.not_tested ? (
        <div className="mb-4">
          <NotTestedBox title={current.not_tested.title} items={current.not_tested.items} />
        </div>
      ) : null}

      {error ? (
        <div className="mb-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      <p data-testid="disclaimer" className="mb-6 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        {current.disclaimer}
      </p>

      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search results" placeholder="Search tests and results" />
        <FilterSelect label="Result" value={statusFilter} options={statusOptions} onChange={setStatusFilter} />
      </Toolbar>

      <TableWithPanel panelOpen={selected !== null} table={listing} panel={panel} />
    </section>
  );
}
