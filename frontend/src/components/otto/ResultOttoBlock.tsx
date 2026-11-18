import type { OttoResultBlock } from "../../api";
import { LedgerView } from "../advisories/parts";
import { ItemLinkView } from "../related";
import { FromOttoTag } from "./ProposalCard";

const H = "text-[13px] font-semibold text-slate-100";
const LIST = "mt-1 list-disc space-y-1 pl-5 text-[13px] text-slate-300 marker:text-slate-500";

/** Phase 5c, on a result of an advisory check: where the check came from. The advisory and the test pack, the test's
 * design by its fingerprint, how the test did when it was tried on public copies, every decision on Otto's proposal
 * with who and when, and the Otto ledger entries of the check and of those decisions. Every word is the backend's.
 * It is a record of where the check came from: it has no pass or fail look and no button. */
export function ResultOttoBlock({ block }: { block?: OttoResultBlock | null }) {
  if (!block) return null;
  return (
    <div data-testid="result-otto" className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-100">
        <FromOttoTag label={block.label} testId="result-otto-label" />
        <span>{block.title}</span>
      </p>
      <p data-testid="result-otto-line" className="mt-1.5 break-words text-[13px] text-slate-300">
        {block.line}{" "}
        <ItemLinkView link={block.advisory.link} testId="result-otto-advisory">
          {block.advisory.label}
        </ItemLinkView>
      </p>

      <div className="mt-3 space-y-3">
        <div data-testid="result-otto-design">
          <h4 className={H}>{block.design.title}</h4>
          <ul className={LIST}>
            {block.design.lines.map((line, i) => (
              <li key={i} className="break-all">
                {line}
              </li>
            ))}
          </ul>
        </div>

        {block.trial ? (
          <div data-testid="result-otto-trial">
            <h4 className={H}>{block.trial.title}</h4>
            <ul className={LIST}>
              {block.trial.lines.map((line, i) => (
                <li key={i} className="break-words">
                  {line}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div data-testid="result-otto-decisions" data-count={block.decisions.count}>
          <h4 className={H}>
            {block.decisions.title} <span className="font-normal tabular-nums text-slate-500">({block.decisions.count})</span>
          </h4>
          {block.decisions.rows.length > 0 ? (
            <ol className="mt-1 space-y-1 text-[13px] text-slate-300">
              {block.decisions.rows.map((row) => (
                <li key={row.number} data-testid="result-otto-decision" className="break-words">
                  {row.line}
                </li>
              ))}
            </ol>
          ) : (
            <p data-testid="result-otto-no-decision" className="mt-1 break-words text-[13px] text-slate-300">
              {block.decisions.empty}
            </p>
          )}
          <p className="mt-1 break-words text-xs text-slate-400">{block.decisions.footnote}</p>
        </div>

        <LedgerView ledger={block.ledger} />
      </div>

      <p data-testid="result-otto-note" className="mt-2 break-words text-xs text-slate-400">
        {block.note}
      </p>
    </div>
  );
}
