import type { Impact, ImpactLine, ImpactPart } from "../../api";
import { ItemLinkView } from "../related";
import { SourceTag, StatusChip } from "../ui";

/** Phase 4e: one place the part is used. The name opens that item (in this assessment, or the one it names). */
function Line({ line }: { line: ImpactLine }) {
  return (
    <li data-testid="impact-line" className="min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {line.link ? (
          <ItemLinkView
            link={line.link}
            testId="impact-link"
            className="font-medium text-sky-300 underline-offset-2 hover:underline"
          >
            {line.text}
          </ItemLinkView>
        ) : (
          <span className="font-medium text-slate-100">{line.text}</span>
        )}
        {line.chip ? <StatusChip label={line.chip} tone="neutral" size="sm" testId="impact-chip" /> : null}
        <SourceTag>{line.tag}</SourceTag>
      </div>
      <p className="mt-0.5 break-words text-[13px] text-slate-400">{line.sub}</p>
    </li>
  );
}

function Part({ part, testId }: { part: ImpactPart; testId: string }) {
  return (
    <div data-testid={testId} className="mt-3">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{part.title}</h4>
      {part.lines.length > 0 ? (
        <ul className="mt-1.5 space-y-2">
          {part.lines.map((line, i) => (
            <Line key={i} line={line} />
          ))}
        </ul>
      ) : (
        <p data-testid="impact-none" className="mt-1 text-[13px] text-slate-400">
          {part.none}
        </p>
      )}
    </div>
  );
}

/** "What this change touches" on a fix, "Where it is used" on a library (phase 4e). Every place, sentence and count is
 * the backend's: this only draws them. It has no button: its links only open pages. */
export function ImpactBlock({ impact }: { impact: Impact | null | undefined }) {
  if (!impact) return null;
  return (
    <section
      data-testid="impact"
      data-count={impact.count}
      aria-label={impact.title}
      className="rounded-xl border border-slate-700 bg-slate-900 p-4"
    >
      <h3 className="text-[15px] font-semibold text-slate-50">{impact.title}</h3>
      <p data-testid="impact-count" className="mt-1 text-sm font-semibold text-slate-100">
        {impact.count_line}
      </p>
      <Part part={impact.here} testId="impact-here" />
      <Part part={impact.elsewhere} testId="impact-elsewhere" />
      {impact.notes.length > 0 ? (
        <ul className="mt-3 space-y-1 text-xs text-slate-400">
          {impact.notes.map((note, i) => (
            <li key={i} data-testid="impact-note">
              {note}
            </li>
          ))}
        </ul>
      ) : null}
      {impact.compatible || impact.connect ? (
        <dl className="mt-3 grid gap-x-4 gap-y-2.5 border-t border-slate-800 pt-3 text-sm @md:grid-cols-[minmax(8rem,12rem)_minmax(0,1fr)]">
          {impact.compatible ? (
            <>
              <dt className="font-medium text-slate-300">{impact.compatible.title}</dt>
              <dd data-testid="impact-compatible" className="min-w-0 text-slate-200">
                {impact.compatible.text}
              </dd>
            </>
          ) : null}
          {impact.connect ? (
            <>
              <dt className="font-medium text-slate-300">{impact.connect.title}</dt>
              <dd data-testid="impact-connect" className="min-w-0 text-slate-200">
                {impact.connect.text}
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </section>
  );
}
