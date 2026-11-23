import type { ReactNode } from "react";
import type { ChangeBadge, ChangeSection, ChangeStep, RichText, Source } from "../../api";
import { RichTextView, WhereFromTag } from "../ui";

const CELL_MONO = "whitespace-nowrap font-mono text-xs text-slate-200";
const TH =
  "border-b border-slate-800 px-2.5 py-1.5 text-left align-bottom text-xs font-medium uppercase tracking-wide text-slate-400";

// One look for each badge look. The badge always carries its words and a symbol, so nothing depends on colour alone.
const BADGES: Record<ChangeBadge["look"], { symbol: string; className: string }> = {
  pass: { symbol: "✓", className: "border-sky-400/60 bg-sky-400/10 text-sky-100" },
  fail: { symbol: "✕", className: "border-amber-400/70 bg-amber-400/15 text-amber-100" },
  warn: { symbol: "?", className: "border-dashed border-slate-400 bg-slate-800 text-slate-100" },
  neutral: { symbol: "•", className: "border-slate-500 bg-slate-700/40 text-slate-100" },
};

/** A badge exactly as the backend worded it. */
export function ChangeBadgeView({ badge, testId = "change-badge" }: { badge: ChangeBadge; testId?: string }) {
  const look = BADGES[badge.look] ?? BADGES.neutral;
  return (
    <span
      data-testid={testId}
      data-look={badge.look}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${look.className}`}
    >
      <span aria-hidden="true" className="font-mono">
        {look.symbol}
      </span>
      {badge.label}
    </span>
  );
}

const STEP_LOOKS: Record<ChangeStep["state"], { symbol: (n: number) => string; className: string }> = {
  done: { symbol: () => "✓", className: "border-sky-400/60 text-sky-100" },
  now: { symbol: () => "…", className: "border-slate-400 bg-slate-800 text-slate-100" },
  off: { symbol: (n) => String(n), className: "border-slate-800 text-slate-500" },
  failed: { symbol: () => "✗", className: "border-amber-400/70 bg-amber-400/10 text-amber-100" },
};

/** The row of small step boxes. Draws nothing when there are no steps. */
export function Steps({ steps }: { steps: ChangeStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ol data-testid="change-steps" className="mt-3 flex flex-wrap gap-2">
      {steps.map((step, i) => {
        const look = STEP_LOOKS[step.state] ?? STEP_LOOKS.off;
        return (
          <li
            key={step.key}
            data-testid="change-step"
            data-step={step.key}
            data-state={step.state}
            className={`min-w-[7.5rem] flex-1 rounded-lg border px-2.5 py-1.5 text-xs ${look.className}`}
          >
            <span className="flex items-center gap-1.5 font-semibold">
              <span aria-hidden="true" className="font-mono">
                {look.symbol(i + 1)}
              </span>
              {step.label}
            </span>
            {step.text ? <span className="mt-0.5 block text-slate-400">{step.text}</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

/** A long setting wraps only after a colon or a space, never inside a name. The copied text has no extra characters. */
function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="mt-1 whitespace-pre-wrap rounded bg-slate-900 p-2 font-mono text-xs leading-5 text-slate-200">
      {code.split("\n").map((line, i) => (
        <span key={i} className="block" style={{ paddingLeft: "2ch", textIndent: "-2ch" }}>
          {line.split(":").map((piece, j, all) => (
            <span key={j}>
              <span className="whitespace-nowrap">
                {piece}
                {j < all.length - 1 ? ":" : ""}
              </span>
              {j < all.length - 1 ? <wbr /> : null}
            </span>
          ))}
        </span>
      ))}
    </pre>
  );
}

const H4 = "text-[13px] font-semibold text-slate-100";

/** A table the view sends: the first column is the row label, every cell is a sentence of rich parts. */
export function RichTable({
  columns,
  rows,
  columnTags = [],
}: {
  columns: string[];
  rows: { label: ReactNode; cells: RichText[] }[];
  /** 22 November 2026: where each column came from (a try: the server as measured before, live; each copy, lab). */
  columnTags?: (Source | null)[];
}) {
  return (
    <div className="mt-2 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 px-3 py-1">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            {columns.map((column, i) => (
              <th key={i} scope="col" className={TH}>
                {column}
                {columnTags[i] ? (
                  <span className="mt-1 block font-normal normal-case tracking-normal">
                    <WhereFromTag tag={columnTags[i]} testId="column-source-tag" />
                  </span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-slate-800 last:border-b-0">
              <th scope="row" className="px-2.5 py-2 text-left align-top font-medium text-slate-100">
                {row.label}
              </th>
              {row.cells.map((cell, c) => (
                <td key={c} className="px-2.5 py-2 align-top text-slate-200">
                  <RichTextView parts={cell} mono={CELL_MONO} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One section of the change: a table, a list of places with the exact lines, or plain paragraphs. */
export function Section({ section }: { section: ChangeSection }) {
  return (
    <div data-testid="change-section" data-kind={section.kind} className="mt-4">
      <h4 className={H4}>{section.title}</h4>
      {section.kind === "table" ? (
        <RichTable
          columns={section.columns}
          rows={section.rows.map(([first, ...rest]) => ({
            label: first ? <RichTextView parts={first} mono={CELL_MONO} /> : null,
            cells: rest,
          }))}
        />
      ) : section.kind === "lines" ? (
        <>
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 px-3 py-1">
            <table className="w-full border-collapse text-[13px]">
              <tbody>
                {section.rows.map((row, i) => (
                  <tr key={i} className="border-b border-slate-800 last:border-b-0">
                    <th scope="row" className="w-1/4 px-2.5 py-2 text-left align-top font-medium text-slate-100">
                      {row.place}
                    </th>
                    <td className="px-2.5 py-2 align-top text-slate-200">
                      {row.lead ? <p>{row.lead}</p> : null}
                      <CodeBlock code={row.code} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {section.note ? <p className="mt-1.5 text-xs text-slate-400">{section.note}</p> : null}
        </>
      ) : (
        <div className="mt-1 space-y-1.5 text-sm text-slate-300">
          {section.paragraphs.map((parts, i) => (
            <p key={i}>
              <RichTextView parts={parts} mono="whitespace-nowrap font-mono text-[0.92em] text-slate-200" />
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
