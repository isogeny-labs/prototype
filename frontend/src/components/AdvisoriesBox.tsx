import type { Advisories } from "../api";
import { SourceTag } from "./ui";

/** Published advisories for a version. Information from the advisory, never a result: no pass or fail look. */
export function AdvisoriesBox({ advisories }: { advisories?: Advisories | null }) {
  if (!advisories || advisories.items.length === 0) return null;
  return (
    <div data-testid="advisories" className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="text-sm font-medium text-slate-100">
        {advisories.title}
        {advisories.tag ? (
          <>
            {" "}
            <SourceTag>{advisories.tag}</SourceTag>
          </>
        ) : null}
      </p>
      <ul className="mt-2 space-y-2.5">
        {advisories.items.map((item, i) => (
          <li key={`${item.id}-${i}`} data-testid="advisory-item" className="text-[13px] text-slate-300">
            <span className="font-mono font-semibold text-slate-100">{item.id}</span> {item.text}
            {item.link ? (
              <>
                {" "}
                {item.href && item.href.startsWith("https://") ? (
                  <a href={item.href} target="_blank" rel="noreferrer noopener" className="underline hover:text-slate-100">
                    {item.link}
                  </a>
                ) : (
                  item.link
                )}
              </>
            ) : null}
            {item.covered ? <span className="mt-0.5 block text-xs text-slate-400">{item.covered}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
