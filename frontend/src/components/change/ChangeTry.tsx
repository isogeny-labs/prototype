import { useState } from "react";
import type { TryView } from "../../api";
import { ResultDetail } from "../lab/ResultDetail";
import { StatusView, WhereFromTag } from "../ui";
import { ChangeClients } from "./ChangeClients";
import { RichTable } from "./ChangeParts";

const VERDICTS: Record<NonNullable<TryView["verdict"]>["look"], string> = {
  pass: "border-sky-400/50 bg-sky-400/10",
  fail: "border-amber-400/60 bg-amber-400/10",
  warn: "border-slate-500 bg-slate-800",
};

function Evidence({
  label,
  result,
  onViewFix,
}: {
  label: string;
  result: TryView["results"][number]["result"];
  onViewFix: (fixId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const id = `change-evidence-${result.run_id}`;
  return (
    <div data-testid="change-evidence" className="mt-2 border-t border-slate-800 pt-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded text-left text-sm text-slate-300 hover:text-slate-100"
      >
        <span aria-hidden="true" className="font-mono text-xs">
          {open ? "▾" : "▸"}
        </span>
        Details and evidence: {label}
      </button>
      {open ? (
        <div id={id}>
          <ResultDetail result={result} busy={false} onViewFix={onViewFix} />
        </div>
      ) : null}
    </div>
  );
}

/** The try on a test copy: while it runs its status; then before and after, the verdict, notes and the evidence behind it. */
export function ChangeTry({ view, onViewFix }: { view: TryView; onViewFix: (fixId: string) => void }) {
  return (
    <div data-testid="change-try" className="mt-4">
      <h4 className="text-[13px] font-semibold text-slate-100">{view.title}</h4>
      {view.running ? (
        <div className="mt-2">
          <StatusView status={view.running} />
        </div>
      ) : (
        <>
          {view.columns.length > 0 ? (
            <RichTable
              columns={view.columns}
              rows={view.rows.map((row) => ({ label: row.label, cells: row.cells }))}
              columnTags={view.column_source_tags ?? []}
            />
          ) : null}
          {view.verdict ? (
            <div
              data-testid="change-verdict"
              data-look={view.verdict.look}
              className={`mt-3 rounded-lg border px-3 py-2.5 text-sm text-slate-100 ${VERDICTS[view.verdict.look] ?? VERDICTS.warn}`}
            >
              <span className="font-semibold">{view.verdict.label}</span>
              {/* 22 November 2026: where the try came from (a test copy on this computer), beside its own word */}
              <WhereFromTag tag={view.source_tag} /> {view.verdict.text}
              {view.source_tag?.note ? " " : null}
              {view.source_tag?.note ? (
                <span data-testid="source-note" className="mt-1 block text-xs text-slate-300">
                  {view.source_tag.note}
                </span>
              ) : null}
            </div>
          ) : null}
          {/* Phase 4e: who can still connect, measured on the first copy. Information only. */}
          {view.clients ? <ChangeClients view={view.clients} /> : null}
          {view.notes.length > 0 ? (
            <ul className="mt-2 space-y-0.5 text-xs text-slate-400">
              {view.notes.map((note, i) => (
                <li key={i} data-testid="change-try-note">
                  {note}
                </li>
              ))}
            </ul>
          ) : null}
          {view.results.map((entry, i) => (
            <Evidence key={i} label={entry.label} result={entry.result} onViewFix={onViewFix} />
          ))}
        </>
      )}
    </div>
  );
}
