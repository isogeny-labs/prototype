import type { ChangePart, DiffLine, FixSection, StrongLabel } from "../../api";

/** The lines of one version of the code. A changed line carries its mark as well as its tint. */
function CodeLines({ lines }: { lines: DiffLine[] }) {
  return (
    <div className="rounded bg-slate-900 py-1.5 font-mono text-xs leading-5">
      {lines.map((line) => {
        const tint =
          line.mark === "-" ? "bg-amber-400/15 text-amber-50" : line.mark === "+" ? "bg-sky-400/15 text-sky-50" : "text-slate-400";
        return (
          <div key={line.n} data-testid="code-line" data-mark={line.mark} className={`grid grid-cols-[3.25rem_1.25rem_1fr] ${tint}`}>
            <span className="select-none pr-2 text-right text-slate-400">{line.n}</span>
            <span className="select-none text-center font-semibold">
              {line.mark === "-" ? "−" : line.mark === "+" ? "+" : ""}
            </span>
            {/* min-w-0 lets a long line wrap inside its column on a narrow screen instead of widening the page. */}
            <span className="min-w-0 whitespace-pre-wrap break-words pr-3">{line.text || " "}</span>
          </div>
        );
      })}
    </div>
  );
}

function Label({ label }: { label: StrongLabel }) {
  return (
    <p className="mb-1 mt-2.5 text-xs text-slate-400">
      {label.lead} <span className="text-slate-200">{label.strong}</span>
      {label.rest}
    </p>
  );
}

function Diff({ part }: { part: ChangePart }) {
  return (
    <div data-testid="change-part" className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="text-sm font-medium text-slate-100">{part.title}</p>
      <p className="mt-0.5 text-xs text-slate-400">{part.why}</p>
      <Label label={part.before_label} />
      <CodeLines lines={part.before} />
      <Label label={part.after_label} />
      <CodeLines lines={part.after} />
    </div>
  );
}

/** The exact lines before and after the change. Nothing here is run; the lines are shown as text. */
export function ChangeBody({ section }: { section: Extract<FixSection, { key: "change" }> }) {
  return (
    <>
      <p className="text-sm text-slate-300">{section.intro}</p>
      {section.parts.map((part, i) => (
        <Diff key={i} part={part} />
      ))}
    </>
  );
}
