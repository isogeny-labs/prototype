import { useEffect, useId, useRef, type ReactNode } from "react";

/** Phase 5a: the parts every page is built from — a page header, summary cards, a table with search and filters, and
 * the right-side detail panel. They draw what they are given; they decide nothing. */

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  eyebrow?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header data-testid="page-header" className="mb-6 flex flex-col gap-4 border-b border-slate-800/80 pb-5 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0 max-w-3xl">
        {eyebrow ? <p className="mb-1 text-xs font-medium uppercase tracking-wider text-slate-500">{eyebrow}</p> : null}
        <h1 className="text-2xl font-semibold tracking-tight text-slate-50">{title}</h1>
        {description ? <div className="mt-1.5 text-sm leading-relaxed text-slate-400">{description}</div> : null}
        {children}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2 md:justify-end">{actions}</div> : null}
    </header>
  );
}

export interface SummaryCard {
  key: string;
  label: string;
  value: ReactNode;
  /** One short line under the number: where it came from or what it counts. */
  sub?: ReactNode;
}

export function SummaryCards({ cards, label }: { cards: SummaryCard[]; label: string }) {
  return (
    <ul aria-label={label} className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map((c) => (
        <li key={c.key} data-testid="summary-card" data-card={c.key} className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
          <p className="text-xs font-medium text-slate-400">{c.label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-slate-50">{c.value}</p>
          {c.sub ? <p className="mt-0.5 text-xs text-slate-500">{c.sub}</p> : null}
        </li>
      ))}
    </ul>
  );
}

export function SearchInput({ value, onChange, label, placeholder }: { value: string; onChange: (v: string) => void; label: string; placeholder?: string }) {
  return (
    <label className="relative block min-w-[12rem] flex-1 sm:max-w-xs">
      <span className="sr-only">{label}</span>
      <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-slate-500">
        ⌕
      </span>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? label}
        className="w-full rounded-lg border border-slate-700 bg-slate-900 py-1.5 pl-7 pr-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/60"
      />
    </label>
  );
}

export function FilterSelect<V extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: V;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-400">
      <span>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as V)}
        className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="mb-3 flex flex-wrap items-center gap-3">{children}</div>;
}

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
}

/** A clean table. A row with `onRowClick` is a button for the keyboard too (Enter or Space opens it). */
export function DataTable<T>({
  label,
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  empty,
  rowTestId,
  headTestId,
}: {
  label: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  empty?: ReactNode;
  rowTestId?: string;
  /** A test id for the header row (so a screen can find its column headings). */
  headTestId?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/30">
      <table aria-label={label} className="w-full border-collapse text-left text-sm">
        <thead>
          <tr data-testid={headTestId} className="border-b border-slate-800 text-xs font-medium uppercase tracking-wider text-slate-500">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`px-4 py-2.5 font-medium ${c.className ?? ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-slate-400">
                {empty ?? "Nothing to show."}
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const key = rowKey(row);
              const selected = selectedKey === key;
              return (
                <tr
                  key={key}
                  data-testid={rowTestId}
                  data-key={key}
                  aria-selected={onRowClick ? selected : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.target !== e.currentTarget) return;
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onRowClick(row);
                          }
                        }
                      : undefined
                  }
                  className={`border-b border-slate-800/70 last:border-b-0 ${
                    onRowClick ? "cursor-pointer transition-colors hover:bg-slate-800/40" : ""
                  } ${selected ? "bg-sky-400/[0.07] shadow-[inset_2px_0_0_var(--color-sky-400)]" : ""}`}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={`px-4 py-3 align-top ${c.className ?? ""}`}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The right-side detail panel: today's detail, technical text and folded evidence for one row, beside the table
 * instead of under it. Escape or the close button shuts it, and focus goes back to where it was.
 */
export function DetailPanel({
  open,
  title,
  subtitle,
  onClose,
  children,
  testId = "detail-panel",
}: {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const before = useRef<Element | null>(null);
  const headingId = useId();
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    before.current = document.activeElement;
    ref.current?.focus({ preventScroll: true });
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close.current();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const back = before.current;
      if (back instanceof HTMLElement && document.contains(back)) back.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <>
      <div aria-hidden="true" onClick={onClose} className="fixed inset-0 z-30 bg-slate-950/60 backdrop-blur-[1px] xl:hidden" />
      <aside
        ref={ref}
        tabIndex={-1}
        role="complementary"
        aria-labelledby={headingId}
        data-testid={testId}
        className="quiet-scroll fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col overflow-y-auto border-l border-slate-800 bg-slate-950 shadow-2xl outline-none xl:sticky xl:top-4 xl:z-auto xl:max-h-[calc(100vh-2rem)] xl:w-auto xl:max-w-none xl:rounded-xl xl:border xl:shadow-none"
      >
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-slate-800 bg-slate-950/95 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            <h2 id={headingId} className="text-base font-semibold text-slate-50">
              {title}
            </h2>
            {subtitle ? <div className="mt-0.5 text-xs text-slate-400">{subtitle}</div> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close details"
            className="rounded-md px-2 py-1 text-lg leading-none text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          >
            ×
          </button>
        </div>
        <div className="flex-1 px-5 py-4">{children}</div>
      </aside>
    </>
  );
}

/** Table on the left, the detail panel on the right when a row is open (on a wide screen; an overlay otherwise). */
export function TableWithPanel({ panelOpen, table, panel }: { panelOpen: boolean; table: ReactNode; panel: ReactNode }) {
  return (
    <div className={`grid gap-4 ${panelOpen ? "xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]" : ""}`}>
      <div className="min-w-0">{table}</div>
      {panel}
    </div>
  );
}

/** The calm empty state: what this is, and the buttons that start it. */
export function EmptyState({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div data-testid="empty-state" className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/30 px-6 py-12 text-center">
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      <div className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-slate-400">{children}</div>
      {actions ? <div className="mt-6 flex flex-wrap justify-center gap-2">{actions}</div> : null}
    </div>
  );
}
