import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { prefs } from "../prefs";

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
  /** Phase 5b: the narrowest this column may get (pixels), so its words never break letter by letter. */
  minWidth?: number;
}

/** Phase 5b: what the table beside a panel knows: whether the panel is open (then it shows its compact form), and the
 * panel's width, which the person can change and which is remembered in this browser for every page. */
interface PanelState {
  open: boolean;
  width: number;
  setWidth: (w: number) => void;
}
const PanelContext = createContext<PanelState | null>(null);
export const PANEL_MIN = 360;
export const PANEL_MAX = 760;
export const PANEL_STEP = 80;

export function usePanelOpen(): boolean {
  return useContext(PanelContext)?.open ?? false;
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
  rowAttrs,
  headTestId,
  compactColumns,
}: {
  label: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  empty?: ReactNode;
  rowTestId?: string;
  /** Extra attributes for a row (for example a data attribute a screen's tests look for). */
  rowAttrs?: (row: T) => Record<string, string | undefined>;
  /** A test id for the header row (so a screen can find its column headings). */
  headTestId?: string;
  /** Phase 5b: the columns shown while the detail panel is open beside the table: the name, one summary status and its
   * key marker. The other columns are in the panel. */
  compactColumns?: Column<T>[];
}) {
  const panelOpen = usePanelOpen();
  const compact = panelOpen && compactColumns !== undefined;
  const shown = compact ? compactColumns : columns;
  return (
    <div data-testid="data-table" data-compact={compact || undefined} className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/30">
      <table aria-label={label} className="w-full border-collapse text-left text-sm [overflow-wrap:normal] [word-break:normal]">
        <thead>
          <tr data-testid={headTestId} className="border-b border-slate-800 text-xs font-medium uppercase tracking-wider text-slate-500">
            {shown.map((c) => (
              <th key={c.key} scope="col" style={c.minWidth ? { minWidth: c.minWidth } : undefined} className={`px-4 py-2.5 font-medium ${c.className ?? ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={shown.length} className="px-4 py-8 text-center text-sm text-slate-400">
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
                  {...(rowAttrs ? rowAttrs(row) : {})}
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
                  {shown.map((c) => (
                    <td key={c.key} style={c.minWidth ? { minWidth: c.minWidth } : undefined} className={`px-4 py-3 align-top ${c.className ?? ""}`}>
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
      if (e.key !== "Escape") return;
      // Escape in a field the person is typing in (a reason, a date) must not close the panel and lose the draft.
      const t = e.target;
      if (t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      close.current();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const back = before.current;
      if (back instanceof HTMLElement && document.contains(back)) back.focus();
    };
  }, [open]);

  const panel = useContext(PanelContext);
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
        {panel ? <PanelEdge panel={panel} /> : null}
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-slate-800 bg-slate-950/95 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            <h2 id={headingId} className="text-base font-semibold text-slate-50">
              {title}
            </h2>
            {subtitle ? <div className="mt-0.5 text-xs text-slate-400">{subtitle}</div> : null}
          </div>
          <div className="flex shrink-0 items-center gap-1">
          {panel ? (
            <>
              <button
                type="button"
                onClick={() => panel.setWidth(panel.width + PANEL_STEP)}
                disabled={panel.width >= PANEL_MAX}
                className="hidden rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40 xl:inline-block"
              >
                Wider
              </button>
              <button
                type="button"
                onClick={() => panel.setWidth(panel.width - PANEL_STEP)}
                disabled={panel.width <= PANEL_MIN}
                className="hidden rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40 xl:inline-block"
              >
                Narrower
              </button>
            </>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close details"
            className="rounded-md px-2 py-1 text-lg leading-none text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          >
            ×
          </button>
          </div>
        </div>
        {/* Phase 5b: inside the panel, content lays itself out by the panel's own width (container queries). */}
        <div className="@container flex-1 px-5 py-4">{children}</div>
      </aside>
    </>
  );
}

/** The panel's left edge: drag it, or use the arrow keys on it, to make the panel wider or narrower. */
function PanelEdge({ panel }: { panel: PanelState }) {
  const start = useRef<{ x: number; w: number } | null>(null);
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the panel"
      aria-valuemin={PANEL_MIN}
      aria-valuemax={PANEL_MAX}
      aria-valuenow={panel.width}
      tabIndex={0}
      data-testid="panel-edge"
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") {
          e.preventDefault();
          panel.setWidth(panel.width + 40);
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          panel.setWidth(panel.width - 40);
        }
      }}
      onPointerDown={(e) => {
        start.current = { x: e.clientX, w: panel.width };
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (start.current) panel.setWidth(start.current.w + (start.current.x - e.clientX));
      }}
      onPointerUp={() => {
        start.current = null;
      }}
      className="absolute inset-y-0 left-0 z-20 hidden w-2 cursor-col-resize rounded-l-xl hover:bg-sky-400/30 focus-visible:bg-sky-400/40 xl:block"
    />
  );
}

/** Table on the left, the detail panel on the right when a row is open (on a wide screen; an overlay otherwise).
 * Phase 5b: the panel has the width the person chose (remembered for every page), and the table beside it switches to
 * its compact form. */
export function TableWithPanel({ panelOpen, table, panel }: { panelOpen: boolean; table: ReactNode; panel: ReactNode }) {
  const [width, setWidthState] = useState<number>(() => clampWidth(prefs.panelWidth()));
  const setWidth = useCallback((w: number) => {
    const next = clampWidth(w);
    setWidthState(next);
    prefs.setPanelWidth(next);
  }, []);
  return (
    <PanelContext.Provider value={{ open: panelOpen, width, setWidth }}>
      <div
        data-testid="table-with-panel"
        style={{ ["--panel-w" as string]: `${width}px` }}
        className={`grid gap-4 ${panelOpen ? "xl:grid-cols-[minmax(0,1fr)_var(--panel-w)]" : ""}`}
      >
        <div className="min-w-0">{table}</div>
        <div className="relative min-w-0 empty:hidden">{panel}</div>
      </div>
    </PanelContext.Provider>
  );
}

function clampWidth(w: number): number {
  return Math.max(PANEL_MIN, Math.min(PANEL_MAX, Math.round(w)));
}

/** Phase 5b: a work group's heading (Verification, Encryption tests, Migration, Dependencies) with its three counts. It
 * folds its rows shut and open, links to where its checks are started, and says why when it is empty. */
export function GroupSection({
  group,
  counts,
  emptyText,
  note,
  startedOn,
  also,
  open,
  onToggle,
  children,
  testId = "group-section",
}: {
  group: { key: string; label: string; question?: string };
  counts?: { open: number; in_progress: number; done: number } | null;
  emptyText?: string | null;
  note?: ReactNode;
  startedOn?: ReactNode;
  also?: ReactNode;
  open: boolean;
  onToggle: () => void;
  children?: ReactNode;
  testId?: string;
}) {
  const headingId = useId();
  return (
    <section data-testid={testId} data-group={group.key} aria-labelledby={headingId} className="mb-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
        <h2 id={headingId} className="m-0">
          <button
            type="button"
            aria-expanded={open}
            onClick={onToggle}
            className="flex items-center gap-2 text-left text-sm font-semibold text-slate-100"
          >
            <span aria-hidden="true" className="inline-block w-3 text-slate-500">
              {open ? "▾" : "▸"}
            </span>
            {group.label}
          </button>
        </h2>
        {counts ? (
          <p data-testid="group-counts" className="text-xs tabular-nums text-slate-400">
            Open {counts.open} · In progress {counts.in_progress} · Done {counts.done}
          </p>
        ) : null}
        {startedOn ? <div className="ml-auto text-xs text-slate-400">{startedOn}</div> : null}
      </div>
      {open ? (
        <div>
          {note ? <p className="mb-2 px-1 text-xs text-slate-400">{note}</p> : null}
          {emptyText ? (
            <p data-testid="group-empty" className="px-1 py-2 text-sm text-slate-400">
              {emptyText}
            </p>
          ) : (
            children
          )}
          {also ? <div data-testid="group-also" className="mt-2 px-1 text-xs text-slate-400">{also}</div> : null}
        </div>
      ) : null}
    </section>
  );
}

/** Phase 5b: a small dialog (the New assessment, Close and Rerun boxes). Escape or Cancel closes it. */
export function Modal({ title, onClose, children, testId }: { title: string; onClose: () => void; children: ReactNode; testId?: string }) {
  const headingId = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const first = ref.current?.querySelector<HTMLElement>("input, select, textarea, button");
    first?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/70 px-4 py-16">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={headingId} data-testid={testId}
           className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl">
        <h2 id={headingId} className="mb-3 text-lg font-semibold text-slate-50">
          {title}
        </h2>
        {children}
      </div>
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
