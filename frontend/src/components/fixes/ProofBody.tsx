import type { FixSection, ProofCell, ProofTable, ProofVerdict, ProofWaiting } from "../../api";
import { ProgressBar, ResultBadge, SourceTag } from "../ui";
import { H } from "./parts";

const GRID = "md:grid-cols-[150px_1fr_1fr_120px]";

/** The column heading, repeated in the cell on narrow screens where the heading row is hidden. */
function CellLabel({ children }: { children: string }) {
  return <p className="mb-1.5 text-xs uppercase tracking-wide text-slate-500 md:hidden">{children}</p>;
}

function ResultCell({ cell, control }: { cell: ProofCell; control?: string }) {
  return (
    <>
      <ResultBadge label={cell.label} tone={cell.tone} />
      <p className="mt-1.5 text-[13px] text-slate-300">{cell.short}</p>
      {control ? <p className="mt-1 text-xs text-slate-400">{control}</p> : null}
    </>
  );
}

/** A test of the proof that has no result yet. The words say whether it is waiting or running. */
function WaitingCell({ title, waiting }: { title: string; waiting: ProofWaiting }) {
  return (
    <div data-testid="proof-waiting" className="flex items-start gap-2 text-[13px] text-slate-300">
      <span aria-hidden="true" className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-slate-500" />
      <div className="min-w-0">
        <p>{waiting.text}</p>
        {waiting.detail ? <p className="text-xs text-slate-400">{waiting.detail}</p> : null}
        {waiting.percent !== null ? <ProgressBar label={`${title}: ${waiting.text}`} percent={waiting.percent} /> : null}
      </div>
    </div>
  );
}

/** One line of the rule check. The words carry the outcome; the mark only repeats it. */
function Check({ ok, text }: { ok: boolean | null; text: string }) {
  return (
    <p data-testid="proof-check" data-ok={String(ok)} className="flex items-start gap-1.5 text-[13px] text-slate-200">
      <span aria-hidden="true" className="font-mono">
        {ok === null ? "•" : ok ? "✓" : "✕"}
      </span>
      <span>{text}</span>
    </p>
  );
}

function Table({ table }: { table: ProofTable }) {
  const [, before, proof, check] = table.columns;
  return (
    <div data-testid="proof-table" className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="text-sm font-medium text-slate-100">
        {table.heading}
        {table.tag ? (
          <>
            {" "}
            <SourceTag>{table.tag}</SourceTag>
          </>
        ) : null}
      </p>
      <p className="mt-0.5 text-xs text-slate-400">{table.need}</p>
      <div
        data-testid="proof-columns"
        className={`mt-2 hidden gap-3 border-b border-slate-800 pb-1.5 text-xs uppercase tracking-wide text-slate-500 md:grid ${GRID}`}
      >
        {table.columns.map((column, i) => (
          <span key={i}>{column}</span>
        ))}
      </div>
      <ul>
        {table.rows.map((row, i) => (
          <li
            key={i}
            data-testid="proof-row"
            data-kind={row.kind}
            className={`grid gap-3 border-b border-slate-800 py-3 last:border-b-0 last:pb-0.5 ${GRID}`}
          >
            <p className="text-sm font-semibold text-slate-100">{row.title}</p>
            <div data-testid="proof-cell-before" className="min-w-0">
              <CellLabel>{before}</CellLabel>
              {row.before ? <ResultCell cell={row.before} /> : null}
            </div>
            <div data-testid="proof-cell-proof" className="min-w-0">
              <CellLabel>{proof}</CellLabel>
              {row.proof ? (
                <ResultCell cell={row.proof} control={row.control} />
              ) : row.waiting ? (
                <WaitingCell title={row.title} waiting={row.waiting} />
              ) : null}
            </div>
            <div>
              <CellLabel>{check}</CellLabel>
              <Check ok={row.check.ok} text={row.check.text} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Why the change is or is not offered. Only a passed proof gets the calm look. */
function Verdict({ verdict }: { verdict: ProofVerdict }) {
  return (
    <div
      data-testid="proof-verdict"
      data-tone={verdict.tone}
      className={`rounded-lg border p-3 ${verdict.tone === "pass" ? "border-sky-400/35 bg-sky-400/5" : "border-amber-400/50 bg-amber-400/5"}`}
    >
      <h4 className={H}>{verdict.title}</h4>
      <div className="mt-1.5 space-y-1">
        {verdict.checks.map((check, i) => (
          <Check key={i} ok={check.ok} text={check.text} />
        ))}
      </div>
      {verdict.shows_title ? <h4 className={`mt-3 ${H}`}>{verdict.shows_title}</h4> : null}
      {verdict.shows.length > 0 ? (
        <div className="mt-1 space-y-1 text-[13px] text-slate-300">
          {verdict.shows.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Every test of the plan, rerun on the changed code. Each result and each check comes from the backend. */
export function ProofBody({ section }: { section: Extract<FixSection, { key: "proof" }> }) {
  return (
    <>
      <p className="text-sm text-slate-300">{section.intro}</p>
      {section.tables.map((table, i) => (
        <Table key={i} table={table} />
      ))}
      {section.verdict ? <Verdict verdict={section.verdict} /> : null}
    </>
  );
}
