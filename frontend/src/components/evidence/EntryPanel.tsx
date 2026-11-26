import { useEffect, useState } from "react";
import { api, errorMessage, type RecordRested, type TimelineEntryDetail } from "../../api";
import { DetailPanel } from "../layout";
import { ProofFold, ProofPart } from "../proof";
import { ItemLinkView } from "../related";
import { ErrorBox, WhereFromTag, formatTime } from "../ui";
import { ResultWord, Sentence, Who } from "./parts";

/** One block of what an entry rested on, or of what came after it: its words, its result words and the way there. */
function Rested({ item }: { item: RecordRested }) {
  return (
    <li data-testid="entry-rested" className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <p className="font-medium text-slate-100">{item.title}</p>
      {item.text ? <p className="mt-1 break-words text-[13px] text-slate-300">{item.text}</p> : null}
      {item.chips.length > 0 ? (
        <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1.5">
          {item.chips.map((chip, i) => (
            <ResultWord key={i} result={chip} name={chip.name} />
          ))}
        </p>
      ) : null}
      {item.link ? (
        <p className="mt-2 text-[13px]">
          <ItemLinkView link={item.link} testId="entry-rested-link">
            {item.link_label ?? "Open"}
          </ItemLinkView>
        </p>
      ) : null}
    </li>
  );
}

const H = "text-xs font-semibold uppercase tracking-wider text-slate-400";

/** The design refactor (26 November 2026): one entry of the record in the side panel, as its story. In the open: what
 * happened, who did it (each person with what they did), each run it started with the reviewer's own word, what it
 * rested on and what came after. Behind one fold, the technical record: ids, commits and fingerprints. It reads the
 * records and repeats them; it decides nothing and starts nothing. */
export function EntryPanel({
  planId,
  entryId,
  onClose,
}: {
  planId: number;
  entryId: string | null;
  onClose: () => void;
}) {
  // What was read, with the entry it was read for: another entry's story is never shown under this one's name.
  const [read, setRead] = useState<{ id: string; detail: TimelineEntryDetail | null; error: string | null } | null>(
    null,
  );
  useEffect(() => {
    if (entryId === null) return;
    let live = true;
    api
      .getTimelineEntry(planId, entryId)
      .then((next) => {
        if (live) setRead({ id: entryId, detail: next, error: null });
      })
      .catch((e: unknown) => {
        if (live) setRead({ id: entryId, detail: null, error: errorMessage(e) });
      });
    return () => {
      live = false;
    };
  }, [planId, entryId]);
  const mine = read && read.id === entryId ? read : null;
  const detail = mine?.detail ?? null;
  const error = mine?.error ?? null;

  const entry = detail?.entry ?? null;
  return (
    <DetailPanel
      open={entryId !== null}
      item={entryId}
      kicker={entry ? `${entry.area.label} · ${entry.kind.label}` : "Timeline"}
      title={detail?.title ?? ""}
      subtitle={entry ? <time dateTime={entry.at}>{formatTime(entry.at)}</time> : undefined}
      onClose={onClose}
    >
      {error ? <ErrorBox>{error}</ErrorBox> : null}
      {detail && entry ? (
        <div data-testid="entry-panel" data-entry={entry.id} className="space-y-5 text-sm">
          <p data-testid="entry-summary" className="break-words">
            <Sentence lead={entry.lead} rest={entry.rest} />
          </p>
          {entry.outcome || entry.counts.length > 0 || entry.marks.length > 0 ? (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              {entry.outcome ? <ResultWord result={entry.outcome} testId="entry-outcome" /> : null}
              {entry.counts.map((c) => (
                <span key={c.label} data-testid="entry-count" className="inline-flex items-center gap-1.5">
                  <ResultWord result={c} /> <span className="tabular-nums text-slate-400">{c.count}</span>
                </span>
              ))}
              {entry.marks.map((mark) => (
                <span
                  key={mark}
                  className="rounded border border-slate-600 px-1.5 py-0.5 text-[11px] font-medium text-slate-200"
                >
                  {mark}
                </span>
              ))}
            </p>
          ) : null}

          <section aria-label="Who" data-testid="entry-who">
            <h3 className={H}>Who</h3>
            <ul className="mt-2 space-y-2">
              {detail.people.map((p, i) => (
                <li
                  key={i}
                  data-testid="entry-person"
                  className="grid gap-x-3 gap-y-0.5 @md:grid-cols-[8rem_minmax(0,1fr)]"
                >
                  <span className="text-xs text-slate-500">{p.role}</span>
                  <span className="min-w-0">
                    <Who who={p.who} />
                    {p.at ? (
                      <time dateTime={p.at} className="ml-2 text-xs text-slate-500">
                        {formatTime(p.at)}
                      </time>
                    ) : null}
                    {p.note ? <span className="mt-0.5 block text-xs text-slate-400">{p.note}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
            {entry.decided_by ? (
              // A result is never a person's: said in the same words on every run.
              <p data-testid="entry-decided-by" className="mt-2 text-[13px] text-slate-300">
                Each result here was {entry.decided_by}.
              </p>
            ) : null}
          </section>

          {entry.runs.length > 0 ? (
            <section aria-label="Runs" data-testid="entry-runs">
              <h3 className={H}>
                The runs it started{" "}
                <span className="font-normal tabular-nums text-slate-500">({entry.runs.length})</span>
              </h3>
              <ul className="mt-2 divide-y divide-slate-800 rounded-lg border border-slate-800">
                {entry.runs.map((run, i) => (
                  <li
                    key={`${run.run_id ?? "v"}-${run.verify_run_id ?? ""}-${i}`}
                    data-testid="entry-run"
                    className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-3 py-2"
                  >
                    <span className="min-w-0">
                      <span className="block break-words font-medium text-slate-100">{run.name}</span>
                      <span className="block text-xs text-slate-400">{run.ran_on}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2">
                      <ResultWord result={run.result} testId="entry-run-result" />
                      <WhereFromTag tag={run.source_tag} />
                      <ItemLinkView link={run.link} testId="entry-run-link">
                        Open
                      </ItemLinkView>
                    </span>
                  </li>
                ))}
              </ul>
              {entry.pending > 0 ? (
                <p role="status" className="mt-2 text-xs text-slate-400">
                  {entry.pending === 1 ? "1 run has" : `${entry.pending} runs have`} no result yet.
                </p>
              ) : null}
            </section>
          ) : null}

          {detail.rested.length > 0 ? (
            <section aria-label={detail.rested_title} data-testid="entry-rested-on">
              <h3 className={H}>{detail.rested_title}</h3>
              <ul className="mt-2 space-y-2">
                {detail.rested.map((item, i) => (
                  <Rested key={i} item={item} />
                ))}
              </ul>
            </section>
          ) : null}

          {detail.after.length > 0 ? (
            <section aria-label={detail.after_title} data-testid="entry-after">
              <h3 className={H}>{detail.after_title}</h3>
              <ul className="mt-2 space-y-2">
                {detail.after.map((item, i) => (
                  <Rested key={i} item={item} />
                ))}
              </ul>
            </section>
          ) : null}

          {entry.link ? (
            <p>
              <ItemLinkView link={entry.link} testId="entry-open">
                {detail.link_label ?? "Open where it happened"}
              </ItemLinkView>
            </p>
          ) : null}

          {detail.record.length > 0 ? (
            <ProofFold kind="record" inside={["Ids, commits and fingerprints"]} testId="entry-record">
              <ProofPart n={1} title={detail.record_title} testId="entry-record-facts">
                <dl className="space-y-2 text-[13px]">
                  {detail.record.map((fact, i) => (
                    <div
                      key={i}
                      data-testid="entry-fact"
                      className="grid gap-x-3 gap-y-0.5 @md:grid-cols-[12rem_minmax(0,1fr)]"
                    >
                      <dt className="text-xs text-slate-500">{fact.label}</dt>
                      <dd className={`min-w-0 break-all text-slate-200 ${fact.mono ? "font-mono text-xs" : ""}`}>
                        {fact.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </ProofPart>
            </ProofFold>
          ) : null}

          <p className="text-xs leading-relaxed text-slate-500">{detail.names_note}</p>
        </div>
      ) : entryId !== null && !error ? (
        <p role="status" className="text-sm text-slate-400">
          Loading…
        </p>
      ) : null}
    </DetailPanel>
  );
}
