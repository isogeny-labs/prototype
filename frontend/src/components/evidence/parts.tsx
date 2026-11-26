import type { ReactNode } from "react";
import type { RecordFilter, RecordResult, RecordWho, RichText } from "../../api";
import { Icon } from "../shell/icons";
import { DemoDataLabel, RichTextView, StatusChip } from "../ui";

/** The design refactor (26 November 2026): the small parts the views of Evidence share. Every word they draw is the
 * record's own, as the backend reads it out; they decide nothing and start nothing. */

// The record's picture names, drawn with the sidebar's line icons.
const ICONS: Record<string, string> = {
  grid: "overview",
  file: "file",
  download: "download",
  signoff: "verify",
  person: "person",
  live: "signal",
  flask: "tests",
  list: "inventory",
  approve: "verify",
  merge: "merge",
  clock: "clock",
  apply: "arrow",
  rollback: "collapse",
};

export function RecordIcon({ icon }: { icon: string }) {
  return (
    <span
      aria-hidden="true"
      data-icon={icon}
      className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-slate-700 bg-slate-900 text-slate-300"
    >
      <Icon name={ICONS[icon] ?? "clock"} className="h-3.5 w-3.5" />
    </span>
  );
}

/** A name on a record: the name it was made under, Demo data where it is a demo reviewer, and the button it was
 * pressed with. Where it came from is its title (and is said in full under the list). */
export function Who({ who, testId = "record-who" }: { who: RecordWho; testId?: string }) {
  return (
    <span
      data-testid={testId}
      data-source={who.source}
      className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5"
    >
      <span title={who.source_label} className={who.recorded ? "font-medium text-slate-100" : "italic text-slate-400"}>
        {who.name}
      </span>
      {who.demo ? <DemoDataLabel /> : null}
      {who.button ? (
        <span data-testid="record-button" className="text-slate-400">
          with {who.button}
        </span>
      ) : null}
    </span>
  );
}

/** A day's heading: the date as the page writes dates, and how many entries the day holds. */
export function DayHeading({ date, count, noun }: { date: string; count: number; noun: [string, string] }) {
  return (
    <h2
      data-testid="record-day"
      data-date={date}
      className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-slate-200"
    >
      <time dateTime={date}>{dayWords(date)}</time>
      <span className="text-xs font-normal tabular-nums text-slate-500">
        {count} {count === 1 ? noun[0] : noun[1]}
      </span>
    </h2>
  );
}

/** "2026-11-25" as "25 November 2026". The day was worked out by the server in the viewer's own zone. */
export function dayWords(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!m) return date;
  const months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];
  const month = months[Number(m[2]) - 1];
  return month ? `${Number(m[3])} ${month} ${m[1]}` : date;
}

/** One row of filters ("Where", "What"): each choice with how many entries it would list. One is always chosen. */
export function FilterChips({
  label,
  filters,
  chosen,
  onChoose,
  testId,
}: {
  label: string;
  filters: RecordFilter[];
  chosen: string;
  onChoose: (key: string) => void;
  testId: string;
}) {
  return (
    <div role="group" aria-label={label} data-testid={testId} className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 w-12 text-xs font-medium uppercase tracking-wider text-slate-500">{label}</span>
      {filters.map((f) => {
        const on = f.key === chosen;
        return (
          <button
            key={f.key}
            type="button"
            aria-pressed={on}
            data-filter={f.key}
            onClick={() => onChoose(f.key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${
              on
                ? "border-sky-400/60 bg-sky-400/10 font-medium text-sky-100"
                : f.count === 0
                  ? "border-slate-800 text-slate-500 hover:text-slate-300"
                  : "border-slate-700 text-slate-300 hover:border-slate-500 hover:text-slate-100"
            }`}
          >
            {f.label}
            <span className="tabular-nums text-slate-500">{f.count}</span>
          </button>
        );
      })}
    </div>
  );
}

/** A result word, drawn as every page draws one. It is the reviewer's, or its own page's, as the record gives it. */
export function ResultWord({ result, name, testId }: { result: RecordResult; name?: string | null; testId?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {name ? <span className="text-xs text-slate-400">{name}</span> : null}
      <StatusChip label={result.label} tone={result.tone} size="sm" wrap testId={testId} />
    </span>
  );
}

/** The sentence of an entry: its bold start and the rest. */
export function Sentence({ lead, rest }: { lead: string; rest: RichText }) {
  return (
    <span className="min-w-0 break-words text-slate-200">
      <strong className="font-semibold text-slate-50">{lead}</strong>
      <RichTextView parts={rest} />
    </span>
  );
}

/** The quiet line under a list that says where names come from. */
export function NamesNote({ children }: { children: ReactNode }) {
  return (
    <p data-testid="names-note" className="mt-6 max-w-3xl text-xs leading-relaxed text-slate-500">
      {children}
    </p>
  );
}

/** The small word over a page of the Evidence section. */
export const EVIDENCE_EYEBROW = "Evidence";
