import type { ReactNode } from "react";
import type { TestProofBlock } from "../../api";
import { ProofFold, ProofPart } from "../proof";
import { AskingCode } from "./AskingCode";

const LABEL =
  "inline-block whitespace-nowrap rounded border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-200";
const TAG =
  "inline-block whitespace-nowrap rounded border border-slate-500 bg-slate-700/40 px-2 py-0.5 text-xs font-medium text-slate-100";

/** The label on everything that came from a public copy sandbox research made, so it is never taken for a pinned library. */
export function SandboxCopyLabel({
  label = "Sandbox copy",
  testId = "sandbox-copy-label",
}: {
  label?: string;
  testId?: string;
}) {
  return (
    <span data-testid={testId} className={LABEL}>
      {label}
    </span>
  );
}

/** One part of the fold, as a page lays it out (see `ProofPart`). */
export interface FoldPart {
  key: string;
  /** Its short name in the fold's header. */
  name: string;
  title: ReactNode;
  extra?: ReactNode;
  body: ReactNode;
}

const HEADLINE = ["affected", "fixed", "control"];

/** How a test was proven, at a glance (the design refactor, 26 November 2026): the three counts that say whether the
 * test tells the affected version from the fixed one, each with the view's own name for that part of the trial (so a
 * fixed version the publisher did not name is never called the publisher's) and what had to happen. Counts only: the
 * counts are the separate reviewer's or the pinned trial script's, and nothing here says Passed or Failed. */
export function ProofTiles({ proof }: { proof: TestProofBlock }) {
  const rows = HEADLINE.map((key) => proof.table.rows.find((r) => r.key === key)).filter(
    (r): r is TestProofBlock["table"]["rows"][number] => Boolean(r),
  );
  if (rows.length === 0) return null;
  return (
    <ul data-testid="proof-tiles" aria-label={proof.title} className="grid min-w-0 gap-2 @lg:grid-cols-3">
      {rows.map((row) => (
        <li
          key={row.key}
          data-testid="proof-tile"
          data-part={row.key}
          className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2.5"
        >
          <p className="break-words text-xs leading-snug text-slate-300">{row.label}</p>
          <p data-testid="proof-tile-count" className="mt-1.5 text-base font-semibold text-slate-50">
            {row.count}
          </p>
          <p className="mt-0.5 break-words text-xs text-slate-400">
            {proof.table.columns[2]}: {row.must}
          </p>
        </li>
      ))}
    </ul>
  );
}

/** Sandbox research (a prototype): everything behind how a test was proven, as the numbered parts of the fold: the
 * trial part by part, what was frozen before the first run, the code that asked the library, the public copies, and
 * that it was replayed. Every word and every count is the view's: the counts are the separate reviewer's, and nothing
 * here says Passed or Failed. It only shows; it has nothing to press but its own folds and the code's Show. */
export function proofParts(proof: TestProofBlock): FoldPart[] {
  return [
    {
      key: "trial",
      name: "The trial, part by part",
      title: "The trial, part by part",
      body: (
        <>
          <p data-testid="proof-summary" className="break-words text-[13px] text-slate-200">
            {proof.summary}
          </p>
          {/* One part of the trial under the other in a narrow panel; side by side, as a table reads, in a wide one. */}
          <ul
            data-testid="proof-rows"
            aria-label={proof.table.columns[0]}
            className="mt-2 divide-y divide-slate-800 rounded-md border border-slate-800"
          >
            {proof.table.rows.map((row) => (
              <li
                key={row.key}
                data-testid="proof-row"
                data-part={row.key}
                className="grid min-w-0 gap-x-4 gap-y-0.5 px-3 py-2 text-[13px] @xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1.2fr)_minmax(0,0.9fr)]"
              >
                <p className="min-w-0 break-words text-slate-100">{row.label}</p>
                <p className="min-w-0 break-words text-slate-400">
                  <span className="text-xs text-slate-500">{proof.table.columns[2]}: </span>
                  {row.must}
                </p>
                <p className="min-w-0 break-words text-slate-300">
                  <span className="text-xs text-slate-500">{proof.table.columns[1]}: </span>
                  <span data-testid="proof-count" className="font-medium text-slate-100">
                    {row.count}
                  </span>
                </p>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 break-words text-xs text-slate-400">{proof.table.note}</p>
        </>
      ),
    },
    {
      key: "frozen",
      name: "Frozen before the first run",
      title: "Frozen before the first run",
      body: (
        <>
          <p data-testid="proof-registered" className="break-words text-[13px] text-slate-300">
            {proof.registered.line}
          </p>
          <p data-testid="proof-judged" className="mt-2 break-words text-[13px] text-slate-300">
            {proof.judged}
          </p>
          <details data-testid="proof-pins" className="mt-2 text-xs text-slate-400">
            <summary className="cursor-pointer font-medium text-slate-300 hover:text-slate-100">
              {proof.registered.pins_title}{" "}
              <span className="tabular-nums text-slate-500">({proof.registered.pins.length})</span>
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
        </>
      ),
    },
    {
      key: "code",
      name: "The code that asked the library",
      title: proof.code.title,
      extra: proof.code.label ? (
        <span data-testid="asking-code-label" className={TAG}>
          {proof.code.label}
        </span>
      ) : undefined,
      body: <AskingCode code={proof.code} bare />,
    },
    {
      key: "copies",
      name: "The public copies",
      title: proof.copies.title,
      body: (
        <div data-testid="proof-copies" className="min-w-0">
          <ul className="list-disc space-y-1 pl-5 text-[13px] text-slate-300 marker:text-slate-500">
            {proof.copies.rows.map((copy) => (
              <li key={copy.version} data-testid="proof-copy" className="break-words [overflow-wrap:anywhere]">
                {copy.line}
                {copy.published ? <span className="text-slate-400"> Published on {copy.published}.</span> : null}
                {copy.helpers_line ? <span className="block text-slate-400">{copy.helpers_line}</span> : null}
              </li>
            ))}
          </ul>
          {proof.copies.left_out.length > 0 ? (
            <ul
              data-testid="proof-left-out"
              className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-slate-400 marker:text-slate-600"
            >
              {proof.copies.left_out.map((line, i) => (
                <li key={i} className="break-words">
                  {line}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="mt-1.5 break-words text-xs text-slate-400 [overflow-wrap:anywhere]">
            {proof.copies.image_line}
          </p>
          <p className="mt-1 break-words text-xs text-slate-400">{proof.copies.trust_line}</p>
        </div>
      ),
    },
    {
      key: "replay",
      name: "The replay",
      title: "The replay",
      body: (
        <p data-testid="proof-replayed" className="break-words text-[13px] text-slate-300">
          {proof.replayed}
        </p>
      ),
    },
  ];
}

/** How a test was proven, standing by itself: its title with the Sandbox copy label, the three counts at a glance, what
 * it does not show, and the fold with every part. An advisory's panel lays the same pieces out with the rest of the
 * advisory's records (see `AdvisoryPanel`). */
export function ProofBlock({ proof, open = false }: { proof: TestProofBlock; open?: boolean }) {
  const parts = proofParts(proof);
  return (
    <div data-testid="proof-block" className="mt-3 min-w-0 space-y-3">
      <p className="flex flex-wrap items-center gap-2 text-[13px] font-semibold text-slate-100">
        <span>{proof.title}</span>
        <SandboxCopyLabel label={proof.label} />
      </p>
      <ProofTiles proof={proof} />
      <p data-testid="proof-not-shown" className="break-words text-[13px] text-slate-300">
        {proof.not_shown}
      </p>
      <ProofFold kind="proof" inside={parts.map((p) => p.name)} defaultOpen={open}>
        {parts.map((p, i) => (
          <ProofPart key={p.key} n={i + 1} title={p.title} extra={p.extra} testId={`proof-part-${p.key}`}>
            {p.body}
          </ProofPart>
        ))}
      </ProofFold>
    </div>
  );
}
