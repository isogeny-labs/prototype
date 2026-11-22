import type { FixSection } from "../../api";
import { RichTextView, SourceTag } from "../ui";
import { DT, Rich } from "./parts";

/** Repository, branches, commits, fingerprints and mode, and what the proof's tests really ran on. */
export function DetailsBody({ section }: { section: Extract<FixSection, { key: "details" }> }) {
  const ranOn = section.ran_on;
  return (
    <>
      <dl className="grid gap-x-3 gap-y-1.5 text-[13px] sm:grid-cols-[230px_1fr]">
        {section.facts.map((fact, i) => (
          <div key={i} data-testid="detail-fact" className="contents">
            <dt className={DT}>{fact.label}</dt>
            {fact.fingerprint ? (
              // A fingerprint is one long word: it has to be allowed to break anywhere, or it runs off the page.
              <dd className="break-all font-mono text-xs text-slate-200">
                <RichTextView parts={fact.value} mono="font-mono" />
              </dd>
            ) : (
              <dd className="text-slate-200">
                <Rich parts={fact.value} />
              </dd>
            )}
          </div>
        ))}
      </dl>
      {section.note ? <p className="text-xs text-slate-400">{section.note}</p> : null}
      {ranOn ? (
        <div data-testid="ran-on" className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
          <p className="text-sm font-medium text-slate-100">{ranOn.title}</p>
          <p className="mt-1 text-[13px] text-slate-300">
            <Rich parts={ranOn.text} />
          </p>
          <dl className="mt-2 grid gap-x-3 gap-y-1 text-xs sm:grid-cols-[230px_1fr]">
            {ranOn.fingerprints.map((item, i) => (
              <div key={i} className="contents">
                <dt className={DT}>{item.label}</dt>
                <dd className="break-all font-mono text-slate-200">
                  {item.value}
                  {item.tag ? (
                    <>
                      {" "}
                      <SourceTag>{item.tag}</SourceTag>
                    </>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
          {ranOn.note ? <p className="mt-2 text-xs text-slate-400">{ranOn.note}</p> : null}
        </div>
      ) : null}
    </>
  );
}
