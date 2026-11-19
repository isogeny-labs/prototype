import type { ReactNode } from "react";
import type { WhatIf, WhatIfLine } from "../../api";
import { ItemLinkView } from "../related";

const H = "mt-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400";

/** Where a fact is quoted from: the publisher's package file or release notes (a link, when its address is an https
 * one), or a test pack's copy of a publisher's line. The quote is the publisher's own text, word for word. */
function Source({ line }: { line: WhatIfLine }) {
  const source = line.source;
  if (!source) return null;
  return (
    <span data-testid="whatif-source" className="mt-0.5 block text-xs text-slate-400">
      {source.url && source.url.startsWith("https://") ? (
        <a href={source.url} target="_blank" rel="noreferrer noopener" data-testid="whatif-source-link" className="underline underline-offset-2 hover:text-slate-100">
          {source.title}
        </a>
      ) : (
        <span>{source.title}</span>
      )}
      {source.read_on ? <span>, read on {source.read_on}</span> : null}
      {source.quote ? (
        <code data-testid="whatif-quote" className="mt-0.5 block whitespace-pre-wrap break-words rounded bg-slate-950 px-1.5 py-1 font-mono text-[11px] text-slate-300">
          {source.quote}
        </code>
      ) : null}
    </span>
  );
}

/** Phase 6e, first half: what the app knows about updating one library to one version, in four parts. Every sentence
 * is the server's, from records the app holds; nothing here is a result, and nothing here is the panel's own
 * judgement. The one thing that can be pressed is the try, which is Evidence's own Retest new version: its card is
 * handed in (`tryCard`) and waits for Confirm like every other start. */
export function WhatIfCard({ whatif, tryCard }: { whatif: WhatIf; tryCard: ReactNode | null }) {
  const tried = whatif.test_copy;
  return (
    <div data-testid="whatif-card" data-known={whatif.known ? "yes" : "no"} className="mt-2">
      <h3 className={H}>{whatif.facts_title}</h3>
      <dl data-testid="whatif-facts" className="mt-1 space-y-2">
        {whatif.facts.map((group) => (
          <div key={group.key} data-testid="whatif-group" data-group={group.key}>
            <dt className="text-xs font-medium text-slate-300">{group.title}</dt>
            <dd className="mt-0.5 space-y-1.5">
              {group.lines.map((line, n) => (
                <p key={`${n}-${line.text}`} data-testid="whatif-line" className="break-words text-[13px] text-slate-200">
                  {line.label ? (
                    <span data-testid="whatif-label" className="mr-1.5 inline-block rounded border border-slate-600 px-1 text-[11px] text-slate-300">
                      {line.label}
                    </span>
                  ) : null}
                  {line.text}
                  {line.link ? (
                    <>
                      {" "}
                      <ItemLinkView link={line.link} testId="whatif-link" className="whitespace-nowrap text-xs text-sky-300 underline-offset-2 hover:underline">
                        See where
                      </ItemLinkView>
                    </>
                  ) : null}
                  <Source line={line} />
                </p>
              ))}
              {group.none ? (
                <p data-testid="whatif-none" className="break-words text-[13px] text-slate-400">
                  {group.none}
                </p>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>

      <h3 className={H}>{tried.title}</h3>
      <div data-testid="whatif-try" data-offered={tried.offered ? "yes" : "no"} className="mt-1">
        {tried.offered && tryCard ? (
          <>
            <ul data-testid="whatif-try-changes" className="list-disc space-y-0.5 pl-5 text-xs text-slate-300 marker:text-slate-500">
              {tried.changes.map((change) => (
                <li key={change} className="break-words">
                  {change}
                </li>
              ))}
            </ul>
            <div className="mt-2">{tryCard}</div>
          </>
        ) : (
          <p data-testid="whatif-try-reason" className="break-words text-[13px] text-slate-300">
            {tried.button} is not offered for this. {tried.reason}
          </p>
        )}
      </div>

      <p data-testid="whatif-explanation" className="mt-3 break-words text-[13px] text-slate-300">
        {whatif.explanation}
      </p>

      <h3 className={H}>{whatif.hypotheses_title}</h3>
      <p className="mt-1 break-words text-xs text-slate-400">{whatif.hypotheses_note}</p>
      <ul data-testid="whatif-hypotheses" className="mt-1 list-disc space-y-1 pl-5 text-[13px] text-slate-200 marker:text-slate-500">
        {whatif.hypotheses.map((hypothesis) => (
          <li key={hypothesis.text} data-testid="whatif-hypothesis" className="break-words">
            {hypothesis.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
