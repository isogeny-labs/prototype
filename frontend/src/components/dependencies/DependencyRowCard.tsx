import type { DependencyCell, DependencyRow } from "../../api";
import { ResultDetail } from "../lab/ResultDetail";
import { ViewInFixes } from "../migration/parts";
import { ResultBadge, SecondaryButton, SourceTag, StatusView, formatTime } from "../ui";

/** One answer: the answer, its one label, the first version that can (on a no), the measurement state, agreement. */
function Cell({ cell, title }: { cell: DependencyCell; title: string }) {
  return (
    <div data-testid="dependency-cell" data-question={cell.question} data-answer={cell.answer} data-state={cell.state}
         className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="text-xs text-slate-400">{title}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <ResultBadge label={cell.answer_words} tone={cell.tone} />
        {cell.label_words ? <SourceTag>{cell.label_words}</SourceTag> : null}
      </div>
      <p className="mt-2 text-xs text-slate-300">{cell.reason}</p>
      {cell.first_version_words ? (
        <p data-testid="first-version" className="mt-1 text-xs font-medium text-slate-100">
          {cell.first_version_words}
        </p>
      ) : null}
      <p data-testid="measure-state" className="mt-1 text-xs text-slate-400">
        {cell.state_words}
      </p>
      {cell.agreement_words ? (
        <p data-testid="agreement" data-agreement={cell.agreement ?? undefined}
           className={`mt-1 text-xs ${cell.agreement === "differs" ? "font-medium text-amber-200" : "text-slate-400"}`}>
          {cell.agreement_words}
        </p>
      ) : null}
    </div>
  );
}

interface Props {
  row: DependencyRow;
  questions: { key: string; short: string }[];
  busy: boolean;
  detailsOpen: boolean;
  onDetailsOpen: (open: boolean) => void;
  onMeasure: () => void;
  onViewFix: (fixId: string) => void;
}

/** One library of the list. Every word comes from the backend. */
export function DependencyRowCard({ row, questions, busy, detailsOpen, onDetailsOpen, onMeasure, onViewFix }: Props) {
  const titles = Object.fromEntries(questions.map((q) => [q.key, q.short]));
  return (
    <li data-testid="dependency-row" data-row={row.id} className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="break-all font-mono text-sm font-semibold text-slate-100">{row.label}</p>
          <p className="mt-0.5 text-xs text-slate-400">
            {row.via_words}
            {row.library ? ` · ${row.library}` : ""}
          </p>
        </div>
        <div className="flex max-w-xs flex-col items-end gap-1">
          <SecondaryButton disabled={busy || !row.measure.enabled} onClick={onMeasure}>
            {row.measure.label}
          </SecondaryButton>
          {row.job ? <StatusView status={row.job} /> : null}
          {!row.measure.enabled && row.measure.blocked_reason ? (
            <p data-testid="row-measure-blocked" className="text-right text-xs text-slate-400">
              {row.measure.blocked_reason}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-3">
        {row.cells.map((cell) => (
          <Cell key={cell.question} cell={cell} title={titles[cell.question] ?? cell.question} />
        ))}
      </div>

      {row.blocks.length > 0 ? (
        <ul data-testid="row-blocks" className="mt-3 space-y-1 text-sm text-amber-100">
          {row.blocks.map((b, i) => (
            <li key={i}>
              Blocks the {b.track_words} track of <span className="font-mono">{b.system}</span>.{" "}
              <ViewInFixes fixId={b.fix_id} onViewFix={onViewFix} />
            </li>
          ))}
        </ul>
      ) : null}

      {row.lookups.length > 0 || row.measurement ? (
        <details className="mt-3" open={detailsOpen} onToggle={(e) => onDetailsOpen((e.target as HTMLDetailsElement).open)}>
          <summary className="cursor-pointer text-sm font-medium text-slate-200">Details and evidence</summary>
          <div className="mt-2 space-y-3">
            {row.lookups.filter((l) => !l.repeat).map((l, i) => (
              <div key={i} data-testid="lookup-source" className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm">
                <p className="text-slate-100">
                  {l.title} <SourceTag>Release notes say</SourceTag>
                </p>
                <blockquote className="mt-1 border-l-2 border-slate-700 pl-2 text-slate-300">“{l.quote}”</blockquote>
                <p className="mt-1 text-xs text-slate-400">
                  For: {row.lookups.filter((x) => x.url === l.url && x.quote === l.quote).map((x) => x.question_words).join(", ")} · checked {l.checked} ·{" "}
                  {l.url.startsWith("https://") ? (
                    <a href={l.url} target="_blank" rel="noreferrer noopener" className="underline hover:text-slate-100">
                      {l.url}
                    </a>
                  ) : (
                    l.url
                  )}
                </p>
              </div>
            ))}
            {row.measurement ? (
              <div data-testid="measurement" className="space-y-2">
                <p className="text-sm text-slate-200">
                  {row.measurement.copy_label} <SourceTag>Measured on a public copy</SourceTag>
                  {row.measurement.finished_at ? (
                    <span className="text-xs text-slate-400"> · {formatTime(row.measurement.finished_at)}</span>
                  ) : null}
                </p>
                <p className="text-xs text-slate-300">{row.measurement.controls_words}</p>
                {row.same_copy_note ? <p className="text-xs text-slate-400">{row.same_copy_note}</p> : null}
                {row.measurement.result ? <ResultDetail result={row.measurement.result} busy={false} onViewFix={onViewFix} /> : null}
              </div>
            ) : null}
          </div>
        </details>
      ) : null}
    </li>
  );
}
