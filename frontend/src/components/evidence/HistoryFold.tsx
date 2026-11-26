import { useState } from "react";
import { api, errorMessage, type HistoryView } from "../../api";
import { usePlanId } from "../related";
import { FoldLine } from "../foldline";
import { ItemLinkView } from "../related";
import { WhereFromTag, formatTime } from "../ui";
import { RecordIcon, ResultWord } from "./parts";

const NAMES: Record<string, string> = {
  test: "History of this check",
  check: "History of this check",
  claim: "History of this claim",
  fix: "History of this fix",
  change: "History of this change",
  system: "History of this system",
  advisory: "History of this advisory",
  library: "History of this library",
};

/** The design refactor (26 November 2026): "History of this" item, a quiet folded line in every panel. What happened
 * to the item, newest first: each run with the version it ran on, who started it and the reviewer's word, and each
 * decision a person made about it. A line on top says who decides a result. It is asked for when the line is opened,
 * and it only reads. */
export function HistoryFold({ itemKey }: { itemKey: string | null }) {
  const planId = usePlanId();
  const [view, setView] = useState<HistoryView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  if (itemKey === null || planId === null) return null;
  const stamp = `${planId}/${itemKey}`;
  // (another item: what was read for the one before is forgotten)
  const mine = asked === stamp ? view : null;
  const kind = itemKey.split(":", 1)[0] ?? "";

  function read() {
    if (asked === stamp || planId === null || itemKey === null) return;
    setAsked(stamp);
    setView(null);
    setError(null);
    api
      .getHistory(planId, itemKey)
      .then(setView)
      .catch((e: unknown) => setError(errorMessage(e)));
  }

  return (
    <FoldLine
      key={stamp}
      title={mine?.title ?? NAMES[kind] ?? "History of this item"}
      count={mine ? mine.lines.length : null}
      testId="history-fold"
      onToggle={(open) => {
        if (open) read();
      }}
    >
      {asked === stamp && error ? (
        <p role="alert" className="text-[13px] text-rose-300">
          {error}
        </p>
      ) : mine ? (
        <div data-testid="history" data-key={mine.key} className="space-y-3 text-[13px]">
          {mine.decides ? (
            <p
              data-testid="history-decides"
              className="rounded-md border border-slate-800 bg-slate-900/50 px-3 py-2 text-slate-300"
            >
              {mine.decides}
            </p>
          ) : null}
          {mine.lines.length === 0 ? (
            <p data-testid="history-empty" className="text-slate-400">
              {mine.empty_text}
            </p>
          ) : (
            <ol className="space-y-2.5">
              {mine.lines.map((line) => (
                <li
                  key={line.id}
                  data-testid="history-line"
                  data-line={line.id}
                  className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2.5"
                >
                  <RecordIcon icon={line.icon} />
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="break-words font-medium text-slate-100">{line.title}</span>
                      {line.result ? <ResultWord result={line.result} testId="history-result" /> : null}
                      {line.results.map((chip, i) => (
                        <ResultWord key={i} result={chip} name={chip.name} />
                      ))}
                      <WhereFromTag tag={line.source_tag} />
                      {line.marks.map((mark) => (
                        <span
                          key={mark}
                          className="rounded border border-slate-600 px-1.5 py-0.5 text-[11px] font-medium text-slate-200"
                        >
                          {mark}
                        </span>
                      ))}
                    </p>
                    <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-400">
                      {line.at ? <time dateTime={line.at}>{formatTime(line.at)}</time> : null}
                      {line.said ? <span data-testid="history-said">{line.said}</span> : null}
                      {line.decided_by ? <span data-testid="history-decided-by">{line.decided_by}</span> : null}
                    </p>
                    {line.note ? <p className="mt-0.5 break-words text-xs text-slate-400">{line.note}</p> : null}
                    {line.fingerprint ? (
                      <p className="mt-0.5 text-xs text-slate-500">
                        Fingerprint{" "}
                        <span title={line.fingerprint} className="font-mono text-slate-400">
                          {line.fingerprint.slice(0, 12)}
                        </span>
                      </p>
                    ) : null}
                    {line.link ? (
                      <p className="mt-0.5 text-xs">
                        <ItemLinkView link={line.link} testId="history-link">
                          Open
                        </ItemLinkView>
                      </p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          )}
          {mine.notes.map((note, i) => (
            <p key={i} data-testid="history-note" className="text-xs text-slate-400">
              {note}
            </p>
          ))}
          <p className="text-xs">
            <ItemLinkView
              link={{ page: "evidence/timeline", item: null, group: mine.timeline.area }}
              testId="history-timeline"
            >
              See it in the timeline
            </ItemLinkView>
          </p>
        </div>
      ) : (
        <p role="status" className="text-[13px] text-slate-400">
          Loading…
        </p>
      )}
    </FoldLine>
  );
}

/** "History of Fixes", in a page's header: opens the timeline with that page's records already chosen. */
export function HistoryOfPage({ area, page }: { area: string; page: string }) {
  return (
    <ItemLinkView
      link={{ page: "evidence/timeline", item: null, group: area }}
      testId="history-of-page"
      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500 hover:text-slate-50"
    >
      History of {page}
    </ItemLinkView>
  );
}
