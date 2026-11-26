import type { AdvisoryLedger, AdvisoryQuote, AdvisorySource, AdvisoryTrial } from "../../api";
import { formatTime, SourceTag } from "../ui";

/** Phase 5c: the small parts of an advisory's panel. They draw the words the view carries; they word no result. */

/** The heading of one block of the panel. */
export const BLOCK_TITLE = "text-xs font-semibold uppercase tracking-wider text-slate-400";
/** A block of the panel. */
export const BLOCK = "min-w-0 rounded-lg border border-slate-800 p-3";

/** A long fingerprint, cut to its first twelve characters. The whole value stays in the page and shows on hover. */
export function ShortHash({ value }: { value: string }) {
  return (
    <span data-testid="short-hash" title={value} className="font-mono text-slate-300">
      {value.slice(0, 12)}
    </span>
  );
}

/** A source by its name: a link when its address is an https one (a publisher's page), plain text otherwise. */
export function SourceName({ name, href }: { name: string; href: string }) {
  return href.startsWith("https://") ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      data-testid="source-link"
      className="underline underline-offset-2 hover:text-slate-100"
    >
      {name}
    </a>
  ) : (
    <span>{name}</span>
  );
}

/** A line of the publisher's own text, word for word, under its tag: information from the advisory, never a result,
 * so it has no pass or fail look. */
export function QuoteView({ quote, testId }: { quote: AdvisoryQuote; testId?: string }) {
  // A quote can be a raw field of a record, with double quotes of its own ("fixed": "6.5.7"). It is then shown as it
  // stands, in fixed-width letters: a second pair of quotation marks around it would only confuse.
  const raw = quote.text.includes('"');
  return (
    <figure data-testid={testId} className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="break-words border-l-2 border-slate-600 pl-3 text-slate-200">
        {raw ? (
          <code data-testid="quote-raw" className="font-mono text-[13px]">
            {quote.text}
          </code>
        ) : (
          <q>{quote.text}</q>
        )}
      </p>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
        {quote.tag ? <SourceTag>{quote.tag}</SourceTag> : null}
        <span className="min-w-0 break-words">
          <SourceName name={quote.source} href={quote.href} />
          {quote.publisher ? <span>, {quote.publisher}</span> : null}
        </span>
        {quote.read_on ? <span>Read on {quote.read_on}</span> : null}
      </figcaption>
    </figure>
  );
}

/** Every source of an advisory, folded: its short label, its name (a link when https), its publisher and the day it was read. */
export function SourcesView({ sources }: { sources: AdvisorySource[] }) {
  if (sources.length === 0) return null;
  return (
    <details data-testid="advisory-sources" className="mt-2 text-xs text-slate-400">
      <summary className="cursor-pointer font-medium text-slate-300 hover:text-slate-100">
        Sources <span className="tabular-nums text-slate-500">({sources.length})</span>
      </summary>
      <ul className="mt-1.5 space-y-1.5">
        {sources.map((s) => (
          <li key={s.label} data-testid="advisory-source" className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2">
            <span className="font-mono text-slate-500">{s.label}</span>
            <span className="min-w-0 break-words">
              <SourceName name={s.title} href={s.href} />
              {s.publisher ? <span>, {s.publisher}</span> : null}
              {s.read_on ? <span className="block text-slate-500">Read on {s.read_on}</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** How a test (or its design) did when it was tried on public copies: the view's counts, line by line. */
export function TrialView({ trial, bare = false }: { trial: AdvisoryTrial; bare?: boolean }) {
  return (
    <div data-testid="advisory-trial">
      {bare ? null : <h4 className="text-[13px] font-semibold text-slate-100">{trial.title}</h4>}
      <ul
        className={`${bare ? "" : "mt-1 "}list-disc space-y-1 pl-5 text-[13px] text-slate-300 marker:text-slate-500`}
      >
        {trial.lines.map((line, i) => (
          <li key={i} className="break-words">
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Otto's ledger entries, folded: each entry's number, kind, what it is, when, and its short id; then the view's note.
 * The ledger is listed as what it is. It is never drawn as a result. */
export function LedgerView({ ledger }: { ledger: AdvisoryLedger }) {
  return (
    <details data-testid="advisory-ledger" className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
      <summary className="cursor-pointer text-xs font-medium text-slate-300 hover:text-slate-100">
        {ledger.title} <span className="tabular-nums text-slate-500">({ledger.count})</span>
      </summary>
      <ol className="mt-2 space-y-1.5">
        {ledger.entries.map((e) => (
          <li
            key={`${e.seq}-${e.id}`}
            data-testid="advisory-ledger-entry"
            className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 text-xs text-slate-300"
          >
            <span className="tabular-nums text-slate-500">{e.seq}</span>
            <span className="min-w-0">
              <span className="block break-words">{e.what}</span>
              <span className="mt-0.5 flex flex-wrap gap-x-2 text-slate-500">
                <span>{e.kind}</span>
                <time dateTime={e.at}>{formatTime(e.at)}</time>
                <span className="font-mono" title={e.id}>
                  {e.id.slice(0, 12)}
                </span>
              </span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2 break-words text-xs text-slate-400">{ledger.note}</p>
    </details>
  );
}
