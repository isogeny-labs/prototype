import { useRef, useState, type FormEvent, type ReactNode } from "react";
import type { AssessmentCounts, Workspace } from "../../api";
import { useDismiss } from "../ui";

/** Small parts the Projects, Overview and Settings pages share (phase 5a). */

/** "Payments / EU" for a folder id, or "Top level". */
export function folderLabel(workspace: Workspace, id: number | null): string {
  if (id === null) return "Top level";
  const f = workspace.folders.find((x) => x.id === id);
  return f ? [...f.path.map((p) => p.name), f.name].join(" / ") : "Top level";
}

export function folderOptions(workspace: Workspace, opts?: { exclude?: number }): { value: string; label: string }[] {
  const excluded = opts?.exclude;
  return [
    { value: "", label: "Top level" },
    ...workspace.folders
      .filter((f) => !f.archived && f.id !== excluded && !f.path.some((p) => p.id === excluded))
      .map((f) => ({ value: String(f.id), label: folderLabel(workspace, f.id) }))
      .sort((a, b) => a.label.localeCompare(b.label)),
  ];
}

const NOT_YET = <span className="text-slate-500">Not yet</span>;

export function ClaimsCell({ counts }: { counts: AssessmentCounts }) {
  const c = counts.claims;
  if (!c) return <span title="Not verified yet">{NOT_YET}</span>;
  return (
    <span className="tabular-nums">
      {c.checked} checked
      {c.false > 0 ? <span className="block text-xs text-amber-200">{c.false} false</span> : <span className="block text-xs text-slate-500">0 false</span>}
    </span>
  );
}

export function TestsCell({ counts }: { counts: AssessmentCounts }) {
  const t = counts.tests;
  if (!t) return <span title="No test has run yet">{NOT_YET}</span>;
  return (
    <span className="tabular-nums">
      {t.failed} failed
      <span className="block text-xs text-slate-500">of {t.run} run</span>
    </span>
  );
}

export function FixesCell({ counts }: { counts: AssessmentCounts }) {
  const f = counts.fixes;
  if (!f) return <span title="Fixes open once a test has a result or the migration plan has something for it">{NOT_YET}</span>;
  return (
    <span className="tabular-nums">
      {f.open} open
      <span className="block text-xs text-slate-500">of {f.total}</span>
    </span>
  );
}

export const SYSTEM_STATUS_WORDS: { key: "classical" | "hybrid" | "pq_only" | "couldnt_check" | "not_measured"; label: string }[] = [
  { key: "classical", label: "Classical" },
  { key: "hybrid", label: "Hybrid" },
  { key: "pq_only", label: "Post-quantum only" },
  { key: "couldnt_check", label: "Couldn't check" },
  { key: "not_measured", label: "Not measured yet" },
];

export function SystemsCell({ counts }: { counts: AssessmentCounts }) {
  const s = counts.systems;
  if (!s) return <span title="Migration has not measured these systems yet">{NOT_YET}</span>;
  const parts = SYSTEM_STATUS_WORDS.filter((w) => s[w.key] > 0);
  return (
    <ul className="flex flex-col gap-0.5 text-xs tabular-nums">
      {parts.map((w) => (
        <li key={w.key}>
          <span className="text-slate-200">{s[w.key]}</span> <span className="text-slate-400">{w.label}</span>
        </li>
      ))}
    </ul>
  );
}

/** A small form in a card: a name, optionally a destination, and two buttons. */
export function InlineForm({
  title,
  submitLabel,
  initialName,
  nameLabel = "Name",
  destination,
  onSubmit,
  onCancel,
  busy,
  error,
}: {
  title: string;
  submitLabel: string;
  initialName?: string;
  nameLabel?: string;
  destination?: { label: string; options: { value: string; label: string }[]; initial: string } | null;
  onSubmit: (name: string, destination: string) => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string | null;
}) {
  const [name, setName] = useState(initialName ?? "");
  const [dest, setDest] = useState(destination?.initial ?? "");
  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit(name, dest);
  }
  return (
    <form onSubmit={submit} aria-label={title} className="mb-5 rounded-xl border border-slate-700 bg-slate-900/70 p-4">
      <p className="mb-3 text-sm font-semibold text-slate-100">{title}</p>
      <div className="flex flex-wrap items-end gap-3">
        {nameLabel ? (
          <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-xs text-slate-400">
            {nameLabel}
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100"
            />
          </label>
        ) : null}
        {destination ? (
          <label className="flex min-w-[12rem] flex-col gap-1 text-xs text-slate-400">
            {destination.label}
            <select
              value={dest}
              onChange={(e) => setDest(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
            >
              {destination.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-sky-500 px-3.5 py-1.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50"
          >
            {submitLabel}
          </button>
          <button type="button" onClick={onCancel} className="rounded-lg border border-slate-700 px-3.5 py-1.5 text-sm text-slate-200 hover:bg-slate-800">
            Cancel
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className="mt-2 text-sm text-amber-200">
          {error}
        </p>
      ) : null}
    </form>
  );
}

/** A "⋯" button with a short menu of actions. */
export function ActionsMenu({ label, items }: { label: string; items: { label: string; onClick: () => void }[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useDismiss(open, box, () => setOpen(false));
  return (
    <div ref={box} className="relative inline-block" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
      >
        ⋯
      </button>
      {open ? (
        <ul role="menu" aria-label={label} className="absolute right-0 top-full z-30 mt-1 min-w-[11rem] rounded-lg border border-slate-700 bg-slate-950 p-1 shadow-xl">
          {items.map((item) => (
            <li key={item.label} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
                className="block w-full rounded-md px-3 py-1.5 text-left text-sm text-slate-200 hover:bg-slate-800"
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Section({
  title,
  children,
  actions,
  id,
  testId,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  /** Phase 5c: a section a link can open on (Settings, "test-packs"). */
  id?: string;
  testId?: string;
}) {
  return (
    <section id={id} data-testid={testId} aria-label={title} className="mb-6 scroll-mt-20">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
