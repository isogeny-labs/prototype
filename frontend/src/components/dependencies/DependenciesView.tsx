import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { usePanelStamp } from "../../changes";
import { api, errorMessage, MAX_DEPENDENCY_LIST_BYTES, type DependenciesView as View, type DependencyRow } from "../../api";
import { CLOSED_SENTENCE, useReadOnly } from "../../readOnly";
import { DataTable, DetailPanel, FilterSelect, SearchInput, SummaryCards, TableWithPanel, Toolbar, type Column } from "../layout";
import { ViewInFixes } from "../migration/parts";
import { FromOttoTag } from "../otto/ProposalCard";
import { ErrorBox, NameText, SecondaryButton, SourceTag, StatusView, WhereFromTag } from "../ui";
import { AlgoName } from "../plainName";
import { RelatedFor } from "../related";
import { AnswerChip, BlocksMarker, DependencyDetail, OttoMarker } from "./DependencyRowCard";

type RowFilter = "all" | "blocks" | "answered" | "unanswered";

const POLL_MS = 1000;

interface Props {
  importId: number;
  onViewFix: (fixId: string) => void;
  /** A list, a tie or a measurement can change the Migration step and Fixes: the app loads the plan again. */
  onChanged: () => void;
  /** Phase 5b: a library row to open, from a link. */
  openItem?: string | null;
}

/** The Dependencies view of the Migration step (phase 4d). Every answer, label, tie and blocker comes from the backend. */
export function DependenciesView({ importId, onViewFix, onChanged, openItem = null }: Props) {
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [openRow, setOpenRow] = useState<string | null>(openItem && openItem.startsWith("row-") ? openItem : null);
  useEffect(() => {
    if (openItem && openItem.startsWith("row-")) setOpenRow(openItem);
  }, [openItem]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<RowFilter>("all");
  const readOnly = useReadOnly();
  const closePanel = useCallback(() => setOpenRow(null), []);
  const [pollTick, setPollTick] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const changed = useRef(onChanged);
  useEffect(() => {
    changed.current = onChanged;
  }, [onChanged]);

  // Phase 6a: a decision or a start sent from the Otto panel: this view is read again.
  const panelStamp = usePanelStamp();
  useEffect(() => {
    let live = true;
    api
      .getDependencies(importId)
      .then((next) => live && setView(next))
      .catch((e: unknown) => live && setError(errorMessage(e)));
    return () => {
      live = false;
    };
  }, [importId, panelStamp]);

  // The end of a measurement can change the blockers: tell the app.
  const lastBusy = useRef<boolean | null>(null);
  useEffect(() => {
    if (!view) return;
    const before = lastBusy.current;
    lastBusy.current = view.busy;
    if (before && !view.busy) changed.current();
  }, [view]);

  const polling = view !== null && view.busy && !acting;
  useEffect(() => {
    if (!polling) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .getDependencies(importId)
        .then((next) => {
          if (!live) return;
          setView(next);
          setPollTick((n) => n + 1);
        })
        .catch((e: unknown) => {
          if (!live) return;
          setError(errorMessage(e));
          setPollTick((n) => n + 1);
        });
    }, POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [importId, polling, pollTick]);

  if (!view) {
    return error ? (
      <ErrorBox title="The dependency list couldn't be loaded">{error}</ErrorBox>
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  }
  const current = view;

  async function act(call: () => Promise<View>) {
    setActing(true);
    setError(null);
    try {
      setView(await call());
      changed.current();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setActing(false);
    }
  }

  function onFileChosen(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > MAX_DEPENDENCY_LIST_BYTES) {
      setError(`"${file.name}" is larger than 16 MB, which is the most this app reads for a dependency list.`);
      return;
    }
    void act(() => api.addDependencyList(current.plan_id, file));
  }

  const measureAll = current.measure_all;

  // Summary cards: counts from the view's own rows and answers, nothing else.
  const allRows = current.groups.flatMap((g) => g.rows);
  const isAnswered = (row: DependencyRow) => row.cells.some((c) => c.answer === "yes" || c.answer === "no");
  const cards = [
    { key: "libraries", label: "Libraries", value: allRows.length, sub: "in the dependency list" },
    { key: "answered", label: "Answered", value: allRows.filter(isAnswered).length, sub: "libraries with a Yes or No" },
    { key: "blockers", label: "Blockers", value: allRows.reduce((n, r) => n + r.blocks.length, 0), sub: "tracks a library blocks" },
  ];
  const needle = search.trim().toLowerCase();
  const matches = (row: DependencyRow) => {
    if (filter === "blocks" && row.blocks.length === 0) return false;
    if (filter === "answered" && !isAnswered(row)) return false;
    if (filter === "unanswered" && isAnswered(row)) return false;
    return !needle || [row.label, row.library, row.via_words].some((t) => (t ?? "").toLowerCase().includes(needle));
  };
  const selected = allRows.find((r) => r.id === openRow) ?? null;

  // Phase 5b: the library's name (breaking only at spaces and dots), "direct" or "through ..." under it, and the Blocks
  // marker; one column per question with a short heading (plain name, the technical name under it).
  const libraryCell = (row: DependencyRow) => (
    <div className="min-w-0">
      <p className="font-mono text-sm font-medium text-slate-100">
        <NameText text={row.label} />
      </p>
      <p data-testid="via-words" className="mt-0.5 text-xs text-slate-400">
        {row.via_words}
        {row.library ? ` · ${row.library}` : ""}
      </p>
      {/* 22 November 2026: the library is here because your dependency list names it */}
      <span className="mt-1 block">
        <WhereFromTag tag={row.source_tag} />
      </span>
      <BlocksMarker row={row} />
      <OttoMarker row={row} />
      {row.job ? (
        <div className="mt-1.5">
          <StatusView status={row.job} />
        </div>
      ) : null}
    </div>
  );
  const columns: Column<DependencyRow>[] = [
    { key: "library", header: "Library", minWidth: 170, render: libraryCell },
    ...current.questions.map(
      (q, i): Column<DependencyRow> => ({
        key: q.key,
        minWidth: 150,
        header: <AlgoName text={q.title.match(/ML-KEM-768|X25519MLKEM768|ML-DSA-65/)?.[0] ?? q.title} />,
        render: (row) => {
          const cell = row.cells[i];
          return cell ? <AnswerChip cell={cell} /> : null;
        },
      }),
    ),
  ];
  // Beside the open panel: the library and version, its answers in short, and the Blocks marker.
  const compactColumns: Column<DependencyRow>[] = [
    { key: "library", header: "Library", minWidth: 150, render: libraryCell },
    { key: "answers", header: "Answers", minWidth: 110, render: (row) => <span className="text-sm text-slate-200">{row.answers_short}</span> },
  ];

  const filterOptions: { value: RowFilter; label: string }[] = [
    { value: "all", label: "All libraries" },
    { value: "blocks", label: "Blocks a system" },
    { value: "answered", label: "Has a Yes or No" },
    { value: "unanswered", label: "No Yes or No yet" },
  ];

  const lists = (
    <div className="space-y-6">
      {current.groups.map((g) => {
        const shown = g.rows.filter(matches);
        return (
          <section key={g.key} data-testid="dependency-group" aria-label={g.label} className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="font-mono text-base font-semibold text-slate-50">{g.label}</h2>
                <p data-testid="tie-words" className="text-xs text-slate-400">
                  {g.tie_words}
                </p>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                {g.picker.label}
                <select
                  aria-label={`${g.picker.label}: ${g.label}`}
                  value={g.picker.selected}
                  disabled={acting || readOnly}
                  title={readOnly ? CLOSED_SENTENCE : undefined}
                  onChange={(e) => void act(() => api.tieDependency(current.plan_id, g.key, e.target.value))}
                  className="rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
                >
                  {g.picker.options.map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {g.empty_text ? (
              <p className="text-sm text-slate-400">{g.empty_text}</p>
            ) : (
              <DataTable
                label={`Libraries: ${g.label}`}
                columns={columns}
                rows={shown}
                rowKey={(r) => r.id}
                rowTestId="dependency-row"
                compactColumns={compactColumns}
                selectedKey={selected?.id ?? null}
                onRowClick={(r) => setOpenRow((cur) => (cur === r.id ? null : r.id))}
                empty="No libraries match this search."
              />
            )}
          </section>
        );
      })}
    </div>
  );

  const panel = (
    <DetailPanel open={selected !== null} item={selected?.id ?? null} title={selected?.label ?? ""} subtitle={selected?.library ?? undefined} onClose={closePanel}>
      {selected ? (
        <DependencyDetail
          row={selected}
          questions={current.questions}
          busy={acting}
          detailsOpen={open.has(selected.id)}
          onDetailsOpen={(isOpen) =>
            setOpen((prev) => {
              const next = new Set(prev);
              if (isOpen) next.add(selected.id);
              else next.delete(selected.id);
              return next;
            })
          }
          onMeasure={() => void act(() => api.measureDependencies(current.plan_id, selected.id))}
          onViewFix={onViewFix}
          planId={current.plan_id}
          // Phase 5c: a decision on one of Otto's proposals was recorded: this view again (it runs nothing), then the app.
          onDecided={() => void act(() => api.getDependencies(importId))}
        />
      ) : null}
      {selected ? <RelatedFor itemKey={`library:${selected.id}`} /> : null}
    </DetailPanel>
  );

  return (
    <div data-testid="dependencies-view" className="space-y-5">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="max-w-3xl">
          <h2 className="text-lg font-semibold tracking-tight text-slate-50">Dependencies</h2>
          <p data-testid="dependencies-subline" className="mt-1 text-sm text-slate-300">
            {current.subline}
          </p>
          {current.list_file?.not_libraries_text ? (
            <p className="mt-1 text-xs text-slate-400">{current.list_file.not_libraries_text}</p>
          ) : null}
          <p className="mt-1 text-xs text-slate-400">{current.upload.note}</p>
        </div>
        <div className="flex max-w-xs flex-col items-end gap-1.5">
          <div className="flex flex-wrap justify-end gap-2">
            <SecondaryButton disabled={acting || current.busy} onClick={() => fileInput.current?.click()}>
              {current.upload.label}
            </SecondaryButton>
            {measureAll ? (
              <SecondaryButton
                disabled={acting || !measureAll.enabled}
                onClick={() => void act(() => api.measureDependencies(current.plan_id, null))}
              >
                {measureAll.label}
              </SecondaryButton>
            ) : null}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".json,application/json"
            aria-label="Choose a dependency list"
            onChange={onFileChosen}
            className="sr-only"
          />
          {measureAll && !measureAll.enabled && measureAll.blocked_reason ? (
            <p data-testid="measure-all-blocked" className="text-right text-xs text-slate-400">
              {measureAll.blocked_reason}
            </p>
          ) : null}
        </div>
      </header>

      {error ? <ErrorBox>{error}</ErrorBox> : null}

      {allRows.length > 0 ? <SummaryCards label="Dependencies summary" cards={cards} /> : null}

      <ul aria-label="What the labels mean" className="flex flex-wrap gap-3 text-xs text-slate-400">
        {current.legend.map((item) => (
          <li key={item.key}>
            <SourceTag>{item.words}</SourceTag>
          </li>
        ))}
      </ul>

      {current.empty_text ? (
        <p data-testid="dependencies-empty" className="text-sm text-slate-400">
          {current.empty_text}
        </p>
      ) : null}

      {current.systems.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {current.systems.map((s) => (
            <div key={s.key} data-testid="dependency-system" data-system={s.key} className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
              <p className="text-xs text-slate-400">{s.kind_label}</p>
              <p className="text-sm font-semibold text-slate-100">
                <span className="font-mono">{s.name}</span>
                <span className="font-normal text-slate-400"> · from {s.tied_from}</span>
              </p>
              <ul className="mt-2 space-y-1 text-sm text-slate-200">
                {s.blocker_lines.map((line, i) => (
                  <li key={i} data-testid="blocker-line">
                    {line.text}
                    {line.fix_id ? (
                      <>
                        {" "}
                        <ViewInFixes fixId={line.fix_id} onViewFix={onViewFix} />
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
              {/* Phase 5c: what a person accepted from Otto for a library of this system. Its own list: never among the blockers. */}
              {(s.otto_lines ?? []).length > 0 ? (
                <ul data-testid="system-otto-lines" className="mt-2 space-y-1 text-sm text-slate-200">
                  {(s.otto_lines ?? []).map((line, i) => (
                    <li key={i} data-testid="system-otto-line" className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
                      <FromOttoTag testId="system-otto-line-label" />
                      <span className="min-w-0 break-words">{line}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {s.without_answer_text ? <p className="mt-2 text-xs text-slate-300">{s.without_answer_text}</p> : null}
              <p className="mt-2 text-xs text-slate-400">{s.environment_line}</p>
            </div>
          ))}
        </div>
      ) : null}


      {current.groups.length > 0 ? (
        <>
          <Toolbar>
            <SearchInput value={search} onChange={setSearch} label="Search libraries" placeholder="Search libraries" />
            <FilterSelect label="Show" value={filter} options={filterOptions} onChange={setFilter} />
          </Toolbar>
          <TableWithPanel panelOpen={selected !== null} table={lists} panel={panel} />
        </>
      ) : null}
    </div>
  );
}
