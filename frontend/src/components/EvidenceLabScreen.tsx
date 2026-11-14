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
import { ResultDetail } from "./lab/ResultDetail";
import {
  DemoDataLabel,
  ErrorBox,
  ResultBadge,
  RichTextView,
  SecondaryButton,
  SourceTag,
  StatusView,
  saveFile,
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
  label,
}: {
  result: LabResult | null;
  status: RowStatus | null;
  testId: string;
  /** The column heading, repeated on narrow screens where the heading row is hidden. */
  label?: string;
}) {
  return (
    <div data-testid={testId} className="min-w-0">
      {label ? <p className="mb-1.5 text-xs uppercase tracking-wide text-slate-500 md:hidden">{label}</p> : null}
      {result ? (
        <>
          <ResultBadge label={result.label} tone={result.tone} />
          <p className="mt-1.5 text-[13px] text-slate-300">{result.short}</p>
        </>
      ) : status ? (
        <StatusView status={status} />
      ) : null}
    </div>
  );
}

function Row({
  row,
  lab,
  open,
  busy,
  onToggle,
  onMarkReviewed,
  onDigDeeper,
  onViewFix,
}: {
  row: LabRow;
  lab: LabView;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onMarkReviewed: (runId: number) => void;
  onDigDeeper: (runId: number) => void;
  onViewFix: (fixId: string) => void;
}) {
  const beforeAfter = lab.view === "before_after";
  const canOpen = row.result !== null || row.after !== null;
  const detailId = `lab-detail-${row.item_id}`;
  const shown = open && canOpen;

  const title = (
    <h2 className="text-[15px] font-semibold text-slate-100">
      {canOpen ? (
        <button
          type="button"
          aria-expanded={shown}
          aria-controls={detailId}
          className="rounded text-left after:absolute after:inset-0 after:content-['']"
        >
          {row.title}
        </button>
      ) : (
        row.title
      )}
    </h2>
  );

  const caret = (
    <span aria-hidden="true" className="pt-[3px] font-mono text-xs text-slate-300">
      {canOpen ? (shown ? "▾" : "▸") : ""}
    </span>
  );

  return (
    <li
      data-testid="lab-row"
      data-kind={row.kind}
      className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
    >
      {/* The whole header opens the row; the title is the real button for keyboards. */}
      <div
        data-testid="lab-row-header"
        onClick={canOpen ? onToggle : undefined}
        className={`relative grid items-start gap-3 ${
          beforeAfter ? "md:grid-cols-[16px_210px_1fr_1fr]" : "grid-cols-[16px_1fr_auto]"
        } ${canOpen ? "cursor-pointer" : ""}`}
      >
        {caret}
        {beforeAfter ? (
          <>
            <div className="min-w-0">
              {title}
              {row.control_line ? <p className="mt-1 text-xs text-slate-400">{row.control_line}</p> : null}
            </div>
            <Cell result={row.result} status={row.result_status} testId="lab-cell-before" label={lab.columns?.before} />
            <Cell result={row.after} status={row.after_status} testId="lab-cell-after" label={lab.columns?.after} />
          </>
        ) : (
          <>
            <div className="min-w-0">
              {title}
              {row.result ? <p className="mt-0.5 text-sm text-slate-300">{row.result.summary}</p> : null}
              {row.control_line ? <p className="mt-1 text-xs text-slate-400">{row.control_line}</p> : null}
            </div>
            <div className="max-w-[16rem]">
              {row.result ? (
                <ResultBadge label={row.result.label} tone={row.result.tone} />
              ) : row.result_status ? (
                <StatusView status={row.result_status} />
              ) : null}
            </div>
          </>
        )}
      </div>

      {shown ? (
        <div id={detailId}>
          {beforeAfter ? (
            <>
              {row.after ? (
                <ResultDetail
                  result={row.after}
                  heading={lab.columns?.after_heading}
                  busy={busy}
                  onMarkReviewed={onMarkReviewed}
                  onDigDeeper={onDigDeeper}
                  onViewFix={onViewFix}
                />
              ) : null}
              {row.result ? (
                <ResultDetail
                  result={row.result}
                  heading={lab.columns?.before_heading}
                  busy={busy}
                  onMarkReviewed={onMarkReviewed}
                  onDigDeeper={onDigDeeper}
                  onViewFix={onViewFix}
                />
              ) : null}
            </>
          ) : row.result ? (
            <ResultDetail
              result={row.result}
              busy={busy}
              onMarkReviewed={onMarkReviewed}
              onDigDeeper={onDigDeeper}
              onViewFix={onViewFix}
            />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

interface Props {
  planId: number;
  /** "View in Fixes" on a failed result: the app opens the Fixes step on that fix. */
  onViewFix: (fixId: string) => void;
}

export function EvidenceLabScreen({ planId, onViewFix }: Props) {
  const [lab, setLab] = useState<LabView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openRows, setOpenRows] = useState<ReadonlySet<number>>(new Set());
  const [menuOpen, setMenuOpen] = useState(false);
  const [exported, setExported] = useState<EvidenceExport | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useDismiss(menuOpen, menuRef, closeMenu);

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
        <h1 id="lab-title" className="text-xl font-semibold text-slate-50">
          Evidence Lab
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
      const made = await api.exportEvidence(current.plan_id);
      saveFile(made.json.url, made.json.filename);
      // A short gap, so browsers that drop back-to-back downloads keep both.
      await new Promise((resolve) => setTimeout(resolve, 300));
      saveFile(made.html.url, made.html.filename);
      setExported(made);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function toggle(itemId: number) {
    setOpenRows((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  const retest = current.retest;
  const blocked = [
    !retest.can_start && !retest.running ? retest.blocked_reason : null,
    !current.download.can_start ? current.download.blocked_reason : null,
  ].filter((reason, i, all): reason is string => Boolean(reason) && all.indexOf(reason) === i);

  return (
    <section aria-labelledby="lab-title">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="lab-title" className="text-xl font-semibold text-slate-50">
            Evidence Lab
          </h1>
          {current.is_demo ? <DemoDataLabel /> : null}
        </div>
        <div ref={menuRef} className="relative flex shrink-0 flex-wrap gap-2.5">
          <SecondaryButton
            expanded={menuOpen}
            disabled={busy || !retest.can_start}
            onClick={() => setMenuOpen((v) => !v)}
          >
            Retest new version
          </SecondaryButton>
          <SecondaryButton disabled={busy || !current.download.can_start} onClick={() => void download()}>
            Download evidence
          </SecondaryButton>
          {menuOpen ? (
            <div
              role="menu"
              aria-label={retest.menu_title}
              className="absolute right-0 top-[46px] z-10 w-[420px] max-w-[calc(100vw-2rem)] rounded-[10px] border border-slate-600 bg-slate-900 p-1.5 shadow-2xl shadow-black/60"
            >
              <p className="px-2.5 pb-1.5 pt-2 text-xs text-slate-400">{retest.menu_title}</p>
              {retest.versions.map((v) => (
                <button
                  key={v.version}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    setExported(null);
                    void act(() => api.retest(current.plan_id, v.version));
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
              <p className="mt-1.5 border-t border-slate-800 px-2.5 pb-1 pt-2 text-xs text-slate-400">
                {retest.menu_note}
              </p>
            </div>
          ) : null}
        </div>
      </div>

      <p data-testid="lab-subline" className="mt-2 text-sm text-slate-400">
        <RichTextView parts={current.subline} />
      </p>

      {current.code_line ? (
        <p data-testid="lab-code-line" className="mt-1 text-sm text-slate-300">
          <RichTextView parts={current.code_line} />
        </p>
      ) : null}

      {retest.running && retest.progress_text ? (
        <p role="status" data-testid="retest-progress" className="mt-2 text-sm text-slate-300">
          {retest.progress_text}
        </p>
      ) : null}

      {blocked.map((reason) => (
        <p key={reason} data-testid="blocked-reason" className="mt-2 text-xs text-slate-400">
          {reason}
        </p>
      ))}

      {exported ? (
        <div
          role="status"
          data-testid="download-status"
          className="mt-3 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-xs text-slate-300"
        >
          <p>{exported.message}</p>
          <p className="mt-1">
            <span className="text-slate-500">{exported.fingerprint_label}: </span>
            <span data-testid="evidence-fingerprint" className="break-all font-mono text-slate-200">
              {exported.fingerprint}
            </span>
          </p>
          <p className="mt-1 break-words font-mono text-slate-400">{exported.verify_hint}</p>
        </div>
      ) : null}

      {error ? (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      <p data-testid="disclaimer" className="mt-6 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        {current.disclaimer}
      </p>

      <div className="mt-6">
        {current.view === "before_after" && current.columns ? (
          <div
            data-testid="lab-columns"
            className="hidden gap-3 px-[17px] pb-2 text-xs uppercase tracking-wide text-slate-500 md:grid md:grid-cols-[16px_210px_1fr_1fr]"
          >
            <span />
            <span>{current.columns.test}</span>
            <ColumnHeading heading={current.columns.before} note={current.columns.before_note} />
            <ColumnHeading heading={current.columns.after} note={current.columns.after_note} />
          </div>
        ) : null}
        {current.rows.length === 0 ? (
          <p className="text-sm text-slate-400">There are no results yet.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {current.rows.map((row) => (
              <Row
                key={row.item_id}
                row={row}
                lab={current}
                open={openRows.has(row.item_id)}
                busy={busy}
                onToggle={() => toggle(row.item_id)}
                onMarkReviewed={(runId) => void act(() => api.markReviewed(runId))}
                onDigDeeper={(runId) => void act(() => api.digDeeper(runId))}
                onViewFix={onViewFix}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
