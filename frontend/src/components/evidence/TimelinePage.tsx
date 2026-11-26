import { useContext, useEffect, useState } from "react";
import { api, errorMessage, type TimelineEntry, type TimelineView } from "../../api";
import { usePanelStamp } from "../../changes";
import { ItemPageContext, PageHeader, SearchInput, TableWithPanel } from "../layout";
import { ItemLinkView } from "../related";
import { DemoDataLabel, ErrorBox, WhereFromTag, formatTime } from "../ui";
import { EntryPanel } from "./EntryPanel";
import { DayHeading, EVIDENCE_EYEBROW, FilterChips, NamesNote, RecordIcon, ResultWord, Sentence, Who } from "./parts";

const POLL_MS = 1000;

/** One thing that happened: when, what (one sentence), its result words where it is a run, who did it and where. */
function EntryRow({ entry, open, onOpen }: { entry: TimelineEntry; open: boolean; onOpen: () => void }) {
  return (
    <li
      data-testid="timeline-entry"
      data-entry={entry.id}
      data-area={entry.area.key}
      data-kind={entry.kind.key}
      data-apart={entry.apart || undefined}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-current={open ? "true" : undefined}
        onClick={onOpen}
        className={`grid w-full grid-cols-[auto_minmax(0,1fr)] gap-x-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors ${
          open
            ? "border-sky-400/50 bg-sky-400/[0.07]"
            : "border-slate-800 bg-slate-900/30 hover:border-slate-600 hover:bg-slate-800/40"
        }`}
      >
        <RecordIcon icon={entry.icon} />
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <span data-testid="timeline-sentence" className="min-w-0 break-words">
              <Sentence lead={entry.lead} rest={entry.rest} />
            </span>
            <time dateTime={entry.at} className="shrink-0 text-xs tabular-nums text-slate-500">
              {formatTime(entry.at)}
            </time>
          </span>
          {entry.outcome || entry.counts.length > 0 || entry.pending > 0 ? (
            <span data-testid="timeline-results" className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
              {entry.outcome ? <ResultWord result={entry.outcome} testId="timeline-outcome" /> : null}
              {entry.counts.map((c) => (
                <span key={c.label} data-testid="timeline-count" className="inline-flex items-center gap-1">
                  <ResultWord result={c} /> <span className="text-xs tabular-nums text-slate-400">{c.count}</span>
                </span>
              ))}
              {entry.pending > 0 ? (
                <span className="text-xs text-slate-400">
                  {entry.pending === 1 ? "1 run" : `${entry.pending} runs`} with no result yet
                </span>
              ) : null}
            </span>
          ) : null}
          <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
            <Who who={entry.who} />
            {entry.also.map((who, i) => (
              <span key={i} className="inline-flex items-center gap-1.5">
                <span aria-hidden="true">·</span>
                <Who who={who} testId="record-who-also" />
              </span>
            ))}
            {entry.decided_by ? (
              <span data-testid="timeline-decided-by">
                <span aria-hidden="true">· </span>
                {entry.decided_by}
              </span>
            ) : null}
            <span aria-hidden="true">·</span>
            <span data-testid="timeline-area">{entry.area.label}</span>
            {entry.source_tags.map((tag) => (
              <WhereFromTag key={tag.key} tag={tag} />
            ))}
            {entry.marks.map((mark) => (
              <span
                key={mark}
                data-testid="timeline-mark"
                className="rounded border border-slate-600 px-1.5 py-0.5 text-[11px] font-medium text-slate-200"
              >
                {mark}
              </span>
            ))}
          </span>
        </span>
      </button>
    </li>
  );
}

/** The design refactor (26 November 2026): the Timeline, the first view of Evidence. Everything that happened in the
 * assessment, newest first, one day at a time. One entry for one press: the runs a press started are in its entry.
 * Two rows of filters, by place and by kind (never by what a result rests on), and a search. An entry opens its story
 * in the side panel. The page reads the records and repeats them: it words no result, decides none and starts
 * nothing. */
export function TimelinePage({
  planId,
  area = null,
  onArea,
  openItem = null,
}: {
  planId: number;
  /** The place the address names ("History of Fixes" opens the timeline with Fixes chosen). */
  area?: string | null;
  onArea?: (area: string | null) => void;
  /** The entry the address names: it opens in the panel. */
  openItem?: string | null;
}) {
  const [view, setView] = useState<TimelineView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ownArea, setOwnArea] = useState<string | null>(area);
  const [kind, setKind] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [asked, setAsked] = useState("");
  const [openId, setOpenId] = useState<string | null>(openItem);
  const [seenItem, setSeenItem] = useState<string | null>(openItem);
  if (openItem !== seenItem) {
    setSeenItem(openItem);
    setOpenId(openItem);
  }
  const [tick, setTick] = useState(0);
  const chosenArea = onArea ? area : ownArea;
  const panelStamp = usePanelStamp();
  const asPage = Boolean(useContext(ItemPageContext)?.asPage);

  // The search is asked for a moment after the last key, not on every one.
  useEffect(() => {
    const timer = setTimeout(() => setAsked(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let live = true;
    api
      .getTimeline(planId, { area: chosenArea, kind, q: asked })
      .then((next) => {
        if (!live) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId, chosenArea, kind, asked, tick, panelStamp]);

  // While something runs, the record grows: ask again every second.
  const busy = view?.busy === true;
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [busy, view]);

  if (!view) {
    return error ? (
      <ErrorBox title="The timeline couldn't be loaded">{error}</ErrorBox>
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  }

  const chooseArea = (key: string) => {
    const next = key === "all" ? null : key;
    if (onArea) onArea(next);
    else setOwnArea(next);
  };

  const list = (
    <div data-testid="timeline-list">
      {view.days.length === 0 ? (
        <p
          data-testid="timeline-empty"
          className="rounded-xl border border-slate-800 px-4 py-8 text-center text-sm text-slate-400"
        >
          {view.empty_text ?? "Nothing matches."}
        </p>
      ) : (
        view.days.map((day) => (
          <section key={day.date} data-testid="timeline-day" data-date={day.date} className="mb-6">
            <DayHeading date={day.date} count={day.count} noun={["entry", "entries"]} />
            <ol className="space-y-2">
              {day.entries.map((entry) => (
                <EntryRow
                  key={entry.id}
                  entry={entry}
                  open={entry.id === openId}
                  onOpen={() => setOpenId((cur) => (cur === entry.id && !asPage ? null : entry.id))}
                />
              ))}
            </ol>
          </section>
        ))
      )}
      {view.apart ? (
        // Change watch's runs are kept apart: listed under Change watch only, and counted in no other number.
        <p
          data-testid="timeline-apart"
          className="mt-2 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-[13px] text-slate-300"
        >
          <span className="font-medium text-slate-100">
            {view.apart.label} ({view.apart.count}).
          </span>{" "}
          {view.apart.text}{" "}
          <button type="button" onClick={() => chooseArea(view.apart!.area)} className="text-sky-300 hover:underline">
            Show them
          </button>
        </p>
      ) : null}
    </div>
  );

  return (
    <section aria-label={view.title} data-testid="timeline-page">
      <PageHeader
        eyebrow={
          <>
            {EVIDENCE_EYEBROW}
            {view.is_demo ? (
              <>
                {" "}
                <DemoDataLabel />
              </>
            ) : null}
          </>
        }
        title={view.title}
        description={<span data-testid="timeline-subline">{view.subline}</span>}
        actions={
          <ItemLinkView
            link={{ page: "evidence/files", item: null }}
            testId="timeline-files-link"
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500 hover:text-slate-50"
          >
            Evidence files
          </ItemLinkView>
        }
      />
      {error ? (
        <div className="mb-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      <div className="mb-4 space-y-2">
        <FilterChips
          label="Where"
          filters={view.areas}
          chosen={view.chosen.area}
          onChoose={chooseArea}
          testId="timeline-where"
        />
        <FilterChips
          label="What"
          filters={view.kinds}
          chosen={view.chosen.kind}
          onChoose={(key) => setKind(key === "all" ? null : key)}
          testId="timeline-what"
        />
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <SearchInput
            value={search}
            onChange={setSearch}
            label="Search the timeline"
            placeholder="Search what happened"
          />
          <p data-testid="timeline-total" role="status" className="text-xs tabular-nums text-slate-400">
            {view.total === 1 ? "1 entry" : `${view.total} entries`}
          </p>
        </div>
      </div>
      <TableWithPanel
        panelOpen={openId !== null}
        table={list}
        panel={<EntryPanel planId={planId} entryId={openId} onClose={() => setOpenId(null)} />}
      />
      <NamesNote>{view.names_note}</NamesNote>
      <p
        data-testid="disclaimer"
        className="mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300"
      >
        {view.disclaimer}
      </p>
    </section>
  );
}
