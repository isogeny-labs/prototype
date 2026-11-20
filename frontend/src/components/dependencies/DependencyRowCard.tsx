import type { DependencyAdvisory, DependencyCell, DependencyRow, OttoProposal } from "../../api";
import { ResultDetail } from "../lab/ResultDetail";
import { ViewInFixes } from "../migration/parts";
import { FromOttoTag, ProposalCard } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { withPlainName } from "../../plainNames";
import { ProofChip, ResultBadge, SecondaryButton, SourceTag, StatusChip, StatusView, formatTime } from "../ui";
import { ImpactBlock } from "../impact/ImpactBlock";

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
  questions: { key: string; title: string }[];
  busy: boolean;
  detailsOpen: boolean;
  onDetailsOpen: (open: boolean) => void;
  onMeasure: () => void;
  onViewFix: (fixId: string) => void;
  /** Phase 5c: for a decision on one of Otto's proposals for this library. */
  planId: number;
  /** After a decision was recorded: the screen reads its own view again. */
  onDecided: (next: OttoProposal) => void;
}

/** Phase 5c: the links of one "Named by advisory" line: its advisory, the evidence of its check here (when one ran) and
 * Otto's proposed fix (when the pack carries one). */
function AdvisoryLinks({ advisory }: { advisory: DependencyAdvisory }) {
  return (
    <>
      <ItemLinkView link={advisory.advisory_link} testId="dependency-advisory-link">
        {advisory.id}
      </ItemLinkView>
      {advisory.evidence_link ? (
        <ItemLinkView link={advisory.evidence_link} testId="dependency-advisory-evidence">
          See the evidence
        </ItemLinkView>
      ) : null}
      {advisory.fix_link && advisory.fix_label ? (
        <ItemLinkView link={advisory.fix_link} testId="dependency-advisory-fix">
          {advisory.fix_label}
        </ItemLinkView>
      ) : null}
    </>
  );
}

/** Phase 5c: in the table, a library that a published advisory names says so under its name: each advisory's line with
 * its state as the chip's tone ("Named by advisory CVE-...: not yet checked") and the way to the proposed fix; the
 * status a person accepted; and Otto's tag with where each proposal stands. Every word is the view's. A library that
 * no advisory names draws nothing. */
export function OttoMarker({ row }: { row: DependencyRow }) {
  const advisories = row.advisories ?? [];
  const proposals = row.otto_proposals ?? [];
  const first = proposals[0];
  if (advisories.length === 0 && !first && !row.otto_status) return null;
  return (
    <span data-testid="dependency-otto-marker" className="mt-1.5 flex flex-col items-start gap-1">
      {advisories.map((a) => (
        <span key={a.id} data-testid="advisory-marker" data-advisory={a.id} data-state={a.state.key} className="flex flex-col items-start gap-0.5">
          <StatusChip label={a.line} tone={a.state.tone} size="sm" wrap />
          {a.fix_link && a.fix_label ? (
            // The link goes to the fix; a click on it does not also open the row.
            <span onClick={(e) => e.stopPropagation()}>
              <ItemLinkView link={a.fix_link} testId="advisory-marker-fix" className="text-[11px] text-sky-300 underline-offset-2 hover:underline">
                {a.fix_label}
              </ItemLinkView>
            </span>
          ) : null}
        </span>
      ))}
      {row.otto_status ? <StatusChip label={row.otto_status.label} tone={row.otto_status.tone} size="sm" wrap testId="otto-status-marker" /> : null}
      {first ? (
        <span data-testid="proposal-marker" className="flex flex-wrap items-center gap-1">
          <FromOttoTag label={first.label} testId="proposal-marker-label" />
          {proposals.map((p) => (
            <StatusChip key={p.id} label={p.status.word} tone={p.status.tone} size="sm" wrap />
          ))}
        </span>
      ) : null}
    </span>
  );
}

/** The answers of one library as chips, one per question, each with its proof chip: the table's cells. Phase 5b: under
 * every No, the reason in one line ("OpenSSL added this in 3.5.0; you have 3.0.22."). */
export function AnswerChip({ cell }: { cell: DependencyCell }) {
  return (
    <div data-testid="dependency-answer" data-question={cell.question} data-answer={cell.answer} data-state={cell.state} className="flex min-w-0 flex-col items-start gap-1.5">
      <ResultBadge label={cell.answer_words} tone={cell.tone} wrap />
      {cell.label_words ? <ProofChip>{cell.label_words}</ProofChip> : null}
      {cell.no_reason ? (
        <p data-testid="no-reason" className="text-xs leading-snug text-slate-300">
          {cell.no_reason}
        </p>
      ) : null}
    </div>
  );
}

/** Phase 5b: the row's Blocks marker, naming the system and the track; it opens that track on the Roadmap. */
export function BlocksMarker({ row }: { row: DependencyRow }) {
  if (row.blocks.length === 0) return null;
  return (
    <span className="mt-1.5 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
      {row.blocks.map((b) => (
        <ItemLinkView
          key={`${b.system}/${b.track}`}
          link={{ page: "migration/roadmap", item: b.system_key ?? null }}
          testId="blocks-marker"
          className="rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-100 hover:underline"
        >
          {b.words || `Blocks ${b.system} · ${b.track_words}`}
        </ItemLinkView>
      ))}
    </span>
  );
}

/** One library of the list, in the detail panel. Every word comes from the backend. */
export function DependencyDetail({ row, questions, busy, detailsOpen, onDetailsOpen, onMeasure, onViewFix, planId, onDecided }: Props) {
  const titles = Object.fromEntries(questions.map((q) => [q.key, withPlainName(q.title)]));
  const advisories = row.advisories ?? [];
  const proposals = row.otto_proposals ?? [];
  return (
    <div data-testid="dependency-detail" data-row={row.id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-slate-400">
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

      <div className="mt-3 grid gap-2 @2xl:grid-cols-3">
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

      {/* Phase 4e: where this library is used: the software of yours that reaches it, and the other assessments that
          name it. Links only; it runs and decides nothing. */}
      {row.impact ? (
        <div className="mt-3">
          <ImpactBlock impact={row.impact} />
        </div>
      ) : null}

      {/* Phase 5c: what the installed test packs' advisories say about this library, and what Otto proposes for it.
          "Measured" is only ever this assessment's own reviewed result; the view words every line. */}
      {advisories.length > 0 || proposals.length > 0 || row.otto_status ? (
        <section data-testid="dependency-otto" className="mt-3 space-y-3">
          {row.otto_status ? (
            <div data-testid="dependency-otto-status" className="min-w-0 text-sm">
              <StatusChip label={row.otto_status.label} tone={row.otto_status.tone} wrap />
              {row.otto_status.lines.map((line, i) => (
                <p key={i} className="mt-1 break-words text-[13px] text-slate-300">
                  {line}
                </p>
              ))}
            </div>
          ) : null}
          {advisories.length > 0 ? (
            <ul className="space-y-2">
              {advisories.map((a) => (
                <li
                  key={a.id}
                  data-testid="dependency-advisory"
                  data-advisory={a.id}
                  data-state={a.state.key}
                  className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm"
                >
                  <StatusChip label={a.line} tone={a.state.tone} wrap testId="dependency-advisory-line" />
                  <p className="mt-1.5 break-words text-xs text-slate-400">{a.name}</p>
                  <p data-testid="dependency-advisory-detail" className="mt-1.5 break-words text-slate-200">
                    {a.detail}
                  </p>
                  <p data-testid="dependency-advisory-fixed" className="mt-1 break-words text-[13px] text-slate-300">
                    {a.fixed_line}
                  </p>
                  <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
                    <AdvisoryLinks advisory={a} />
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
          {proposals.map((p) => (
            <ProposalCard key={p.id} planId={planId} proposal={p} onDecided={onDecided} />
          ))}
        </section>
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
    </div>
  );
}
