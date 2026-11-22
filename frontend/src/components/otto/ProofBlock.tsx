import type { TestProofBlock } from "../../api";
import { AskingCode } from "./AskingCode";

const LABEL = "inline-block whitespace-nowrap rounded border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-200";

/** The label on everything that came from a public copy sandbox research made, so it is never taken for a pinned library. */
export function SandboxCopyLabel({ label = "Sandbox copy", testId = "sandbox-copy-label" }: { label?: string; testId?: string }) {
  return (
    <span data-testid={testId} className={LABEL}>
      {label}
    </span>
  );
}

/** Sandbox research (a prototype): how a test was proven, as one piece, folded under a proposal's summary. Every word
 * and every count is the view's: the counts are the separate reviewer's, and nothing here says Passed or Failed. The
 * block only shows; it has nothing to press but its own folds and the code's Show. */
export function ProofBlock({ proof, open = false }: { proof: TestProofBlock; open?: boolean }) {
  return (
    <details data-testid="proof-block" open={open} className="mt-3 min-w-0 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
      <summary className="cursor-pointer text-[13px] font-medium text-slate-200 hover:text-slate-100">
        <span className="mr-2">{proof.title}</span>
        <SandboxCopyLabel label={proof.label} />
      </summary>

      <p data-testid="proof-summary" className="mt-2 break-words text-[13px] text-slate-200">
        {proof.summary}
      </p>

      {/* One part of the trial under the other: a table of three columns would not fit a narrow panel. */}
      <ul data-testid="proof-rows" aria-label={proof.table.columns[0]} className="mt-2 divide-y divide-slate-800 rounded-md border border-slate-800">
        {proof.table.rows.map((row) => (
          <li key={row.key} data-testid="proof-row" data-part={row.key} className="min-w-0 px-3 py-2 text-[13px]">
            <p className="break-words text-slate-100">{row.label}</p>
            <p className="mt-0.5 break-words text-slate-300">
              <span className="text-xs text-slate-500">{proof.table.columns[1]}: </span>
              <span data-testid="proof-count" className="font-medium text-slate-100">
                {row.count}
              </span>
            </p>
            <p className="mt-0.5 break-words text-slate-400">
              <span className="text-xs text-slate-500">{proof.table.columns[2]}: </span>
              {row.must}
            </p>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 break-words text-xs text-slate-400">{proof.table.note}</p>

      <p data-testid="proof-registered" className="mt-3 break-words text-[13px] text-slate-300">
        {proof.registered.line}
      </p>
      <details data-testid="proof-pins" className="mt-1.5 text-xs text-slate-400">
        <summary className="cursor-pointer font-medium text-slate-300 hover:text-slate-100">
          {proof.registered.pins_title} <span className="tabular-nums text-slate-500">({proof.registered.pins.length})</span>
        </summary>
        <ul className="mt-1.5 space-y-1">
          {proof.registered.pins.map((pin) => (
            <li key={pin.name} className="min-w-0 break-words">
              <span className="font-mono text-slate-300 [overflow-wrap:anywhere]">{pin.name}</span>{" "}
              <span className="font-mono text-slate-500" title={pin.sha256}>
                {pin.sha256.slice(0, 12)}
              </span>
            </li>
          ))}
        </ul>
      </details>
      <p data-testid="proof-judged" className="mt-2 break-words text-[13px] text-slate-300">
        {proof.judged}
      </p>

      <div className="mt-3">
        <AskingCode code={proof.code} />
      </div>

      <div data-testid="proof-copies" className="mt-3 min-w-0">
        <h4 className="text-[13px] font-semibold text-slate-100">{proof.copies.title}</h4>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-[13px] text-slate-300 marker:text-slate-500">
          {proof.copies.rows.map((copy) => (
            <li key={copy.version} data-testid="proof-copy" className="break-words [overflow-wrap:anywhere]">
              {copy.line}
              {copy.published ? <span className="text-slate-400"> Published on {copy.published}.</span> : null}
              {copy.helpers_line ? <span className="block text-slate-400">{copy.helpers_line}</span> : null}
            </li>
          ))}
        </ul>
        {proof.copies.left_out.length > 0 ? (
          <ul data-testid="proof-left-out" className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-slate-400 marker:text-slate-600">
            {proof.copies.left_out.map((line, i) => (
              <li key={i} className="break-words">
                {line}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="mt-1.5 break-words text-xs text-slate-400 [overflow-wrap:anywhere]">{proof.copies.image_line}</p>
        <p className="mt-1 break-words text-xs text-slate-400">{proof.copies.trust_line}</p>
      </div>

      <p data-testid="proof-replayed" className="mt-3 break-words text-[13px] text-slate-300">
        {proof.replayed}
      </p>
      <p data-testid="proof-not-shown" className="mt-2 break-words text-[13px] text-slate-300">
        {proof.not_shown}
      </p>
    </details>
  );
}
