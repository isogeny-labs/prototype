import type { ReactNode } from "react";
import type { EvidenceBlock, FixLine, LabResult, MetaItem } from "../../api";
import { ResultBadge, SecondaryButton, SourceTag, Spinner, formatTime } from "../ui";

function Box({ title, tag, children }: { title: string; tag?: string | null; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="text-sm font-medium text-slate-100">
        {title}
        {tag ? (
          <>
            {" "}
            <SourceTag>{tag}</SourceTag>
          </>
        ) : null}
      </p>
      {children}
    </div>
  );
}

/** Small facts under a table or a run record. Links are only ever the backend's own source links. */
function Meta({ items }: { items: MetaItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-300">
      {items.map((item, i) => {
        const value =
          item.href && item.href.startsWith("https://") ? (
            <a href={item.href} target="_blank" rel="noreferrer noopener" className="underline hover:text-slate-100">
              {item.value}
            </a>
          ) : (
            item.value
          );
        return (
          <li key={i}>
            {item.label ? <span className="text-slate-500">{item.label}: </span> : null}
            {item.time ? <time dateTime={item.time}>{formatTime(item.time)}</time> : null}
            {item.time && item.value ? " " : null}
            {value}
            {item.tag ? (
              <>
                {" "}
                <SourceTag>{item.tag}</SourceTag>
              </>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-900 p-2 font-mono text-xs text-slate-200">
      {children}
    </pre>
  );
}

function Block({ block }: { block: EvidenceBlock }) {
  if (block.type === "text") {
    return (
      <Box title={block.title} tag={block.tag}>
        <Pre>{block.text}</Pre>
      </Box>
    );
  }
  return (
    <Box title={block.title} tag={block.tag}>
      <div className="overflow-x-auto">
        <table className="mt-1.5 w-full border-collapse text-[13px]">
          <thead>
            <tr>
              {block.columns.map((col, i) => (
                <th
                  key={i}
                  scope="col"
                  className={`border-b border-slate-800 px-2.5 py-1.5 align-bottom text-xs font-medium uppercase tracking-wide text-slate-400 ${
                    col.align === "right" ? "whitespace-nowrap text-right" : "text-left"
                  }`}
                >
                  {col.label.split("\n").map((line, j) => (
                    <span key={j} className="block">
                      {line}
                    </span>
                  ))}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, r) => (
              <tr key={r} className="border-b border-slate-800 last:border-b-0">
                {row.map((cell, c) => {
                  const col = block.columns[c];
                  return (
                    <td
                      key={c}
                      className={`px-2.5 py-2 align-top text-slate-200 ${
                        col?.align === "right" ? "whitespace-nowrap text-right" : "text-left"
                      } ${col?.mono ? "font-mono" : ""}`}
                    >
                      {cell}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Meta items={block.meta} />
      {block.note ? <p className="mt-2 text-xs text-slate-400">{block.note}</p> : null}
    </Box>
  );
}

function Paragraphs({ lines }: { lines: string[] }) {
  return (
    <div className="space-y-1.5 text-sm text-slate-300">
      {lines.map((line, i) => (
        <p key={i}>{line}</p>
      ))}
    </div>
  );
}

const FIX_LINE_LOOKS: Record<FixLine["look"], string> = {
  plain: "border-slate-600 bg-slate-900",
  pass: "border-sky-400/35 bg-sky-400/5",
  fail: "border-amber-400/50 bg-amber-400/5",
  dashed: "border-dashed border-slate-500 bg-slate-900",
};

/** The one line that points a failed result to its fix. The fix itself is only shown in the Fixes step. */
function FixLineView({ line, onViewFix }: { line: FixLine; onViewFix: (fixId: string) => void }) {
  return (
    <div
      data-testid="fix-line"
      data-look={line.look}
      className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-3 py-2 ${FIX_LINE_LOOKS[line.look] ?? FIX_LINE_LOOKS.plain}`}
    >
      <p className="flex min-w-0 items-center gap-2 text-sm text-slate-200">
        {line.busy ? <Spinner className="h-3.5 w-3.5" /> : null}
        <span>
          <span className="font-semibold text-slate-100">{line.lead}</span> {line.rest}
        </span>
      </p>
      <span aria-hidden="true" className="text-slate-400">
        →
      </span>
      <SecondaryButton onClick={() => onViewFix(line.fix_id)}>{line.button}</SecondaryButton>
    </div>
  );
}

const H = "mb-1 text-[13px] font-semibold text-slate-100";
const DT = "mt-2 text-slate-500";

interface Props {
  result: LabResult;
  /** Shown above the detail in the before/after view, e.g. "After: acme-sign 1.4.3, the merged fix (commit c41f0d2)". */
  heading?: string;
  busy: boolean;
  onMarkReviewed: (runId: number) => void;
  onDigDeeper: (runId: number) => void;
  onViewFix: (fixId: string) => void;
}

/** Everything behind one reviewed result. All wording and every verdict come from the backend. */
export function ResultDetail({ result, heading, busy, onMarkReviewed, onDigDeeper, onViewFix }: Props) {
  const locked = result.locked_test;
  const record = result.run_record;
  const research = result.research;

  return (
    <section
      data-testid="result-detail"
      data-run-id={result.run_id}
      aria-label={heading ?? "Result details"}
      className="mt-3.5 flex flex-col gap-4 border-t border-slate-800 pt-3.5"
    >
      {heading ? (
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-slate-400">{heading}</h3>
          <ResultBadge label={result.label} tone={result.tone} />
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h4 className={H}>What happened</h4>
          <Paragraphs lines={result.what_happened.length > 0 ? result.what_happened : [result.summary]} />
        </div>
        <div>
          <h4 className={H}>{result.shows_title}</h4>
          <Paragraphs lines={result.shows} />
        </div>
      </div>

      <div>
        <h4 className={H}>Evidence</h4>
        <div className="space-y-3">
          {result.evidence.map((block, i) => (
            <Block key={i} block={block} />
          ))}

          <Box title={record.title}>
            <dl className="text-xs">
              <dt className={DT}>Command</dt>
              <dd className="break-words font-mono text-slate-200">{record.command}</dd>
              {record.outputs.map((out, i) => (
                <div key={i}>
                  <dt className={DT}>{out.title}</dt>
                  <dd>
                    <Pre>{out.text}</Pre>
                  </dd>
                </div>
              ))}
            </dl>
            <Meta items={record.meta} />
          </Box>

          <Box title={locked.title}>
            <dl data-testid="locked-test" className="text-xs">
              {locked.fields.map((field, i) => (
                <div key={i}>
                  <dt className={DT}>{field.label}</dt>
                  <dd className="text-slate-200">
                    {field.lines.map((line, j) => (
                      <span key={j} className="block">
                        {line}
                      </span>
                    ))}
                  </dd>
                </div>
              ))}
              <dt className={DT}>Locked</dt>
              <dd className="text-slate-200">
                <time dateTime={locked.locked_at}>{formatTime(locked.locked_at)}</time>, {locked.locked_text}
              </dd>
              <dt className={DT}>{locked.fingerprint_label}</dt>
              <dd data-testid="spec-fingerprint" className="break-all font-mono text-slate-200">
                {locked.fingerprint}
              </dd>
            </dl>
            <p className="mt-2 text-xs text-slate-400">{locked.note}</p>
          </Box>
        </div>
      </div>

      <div data-testid="control-outcome" data-outcome={result.control.outcome}>
        <h4 className={H}>Control</h4>
        <p className="text-sm text-slate-300">{result.control.text}</p>
      </div>

      {result.fix_line ? (
        <FixLineView line={result.fix_line} onViewFix={onViewFix} />
      ) : result.suggested_fix !== null ? (
        <div data-testid="suggested-fix" className="rounded-lg border border-sky-400/35 bg-sky-400/5 p-3">
          <h4 className={H}>{result.fix_title}</h4>
          <p className="text-sm text-slate-300">{result.suggested_fix}</p>
        </div>
      ) : null}

      {research ? (
        <div data-testid="research-request" className="rounded-lg border border-dashed border-slate-500 bg-slate-900 p-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <h4 className="text-[13px] font-semibold text-slate-100">{research.title}</h4>
            <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-500 bg-slate-700/40 px-2.5 py-1 text-sm font-semibold text-slate-100">
              <span aria-hidden="true" className="font-mono">
                •
              </span>
              {research.badge}
            </span>
            <span className="text-sm text-slate-300">{research.status_line}</span>
          </div>
          <dl className="mt-2 grid grid-cols-[130px_1fr] gap-x-3 gap-y-1 text-[13px]">
            {research.fields.map((field, i) => (
              <div key={i} className="contents">
                <dt className="text-slate-400">{field.label}</dt>
                <dd className="text-slate-200">{field.value}</dd>
              </div>
            ))}
            <dt className="text-slate-400">Saved</dt>
            <dd className="text-slate-200">
              <time dateTime={research.saved_at}>{formatTime(research.saved_at)}</time>
            </dd>
          </dl>
          <p className="mt-2 text-xs text-slate-400">{research.note}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2.5">
        <SecondaryButton
          pressed={result.reviewed !== null}
          disabled={busy || result.reviewed !== null}
          onClick={() => onMarkReviewed(result.run_id)}
        >
          {result.reviewed ? "Reviewed" : "Mark reviewed"}
        </SecondaryButton>
        <SecondaryButton disabled={busy || research !== null} onClick={() => onDigDeeper(result.run_id)}>
          {research ? "Dig deeper: queued" : "Dig deeper"}
        </SecondaryButton>
        {result.reviewed ? (
          <span data-testid="reviewed-note" className="text-xs text-slate-400">
            {result.reviewed.text} <time dateTime={result.reviewed.at}>{formatTime(result.reviewed.at)}</time>
          </span>
        ) : null}
      </div>
    </section>
  );
}
