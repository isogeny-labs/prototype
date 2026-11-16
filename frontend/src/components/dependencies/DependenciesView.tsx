import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { api, errorMessage, MAX_DEPENDENCY_LIST_BYTES, type DependenciesView as View } from "../../api";
import { ViewInFixes } from "../migration/parts";
import { ErrorBox, SecondaryButton, SourceTag } from "../ui";
import { DependencyRowCard } from "./DependencyRowCard";

const POLL_MS = 1000;

interface Props {
  importId: number;
  onViewFix: (fixId: string) => void;
  /** A list, a tie or a measurement can change the Migration step and Fixes: the app loads the plan again. */
  onChanged: () => void;
}

/** The Dependencies view of the Migration step (phase 4d). Every answer, label, tie and blocker comes from the backend. */
export function DependenciesView({ importId, onViewFix, onChanged }: Props) {
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [pollTick, setPollTick] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const changed = useRef(onChanged);
  useEffect(() => {
    changed.current = onChanged;
  }, [onChanged]);

  useEffect(() => {
    let live = true;
    api
      .getDependencies(importId)
      .then((next) => live && setView(next))
      .catch((e: unknown) => live && setError(errorMessage(e)));
    return () => {
      live = false;
    };
  }, [importId]);

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
  return (
    <div data-testid="dependencies-view" className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <p data-testid="dependencies-subline" className="text-sm text-slate-300">
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
      </div>

      {error ? <ErrorBox>{error}</ErrorBox> : null}

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
              {s.without_answer_text ? <p className="mt-2 text-xs text-slate-300">{s.without_answer_text}</p> : null}
              <p className="mt-2 text-xs text-slate-400">{s.environment_line}</p>
            </div>
          ))}
        </div>
      ) : null}

      {current.groups.map((g) => (
        <section key={g.key} data-testid="dependency-group" aria-label={g.label} className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-800 pb-2">
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
                disabled={acting}
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
            <ul className="space-y-3">
              {g.rows.map((row) => (
                <DependencyRowCard
                  key={row.id}
                  row={row}
                  questions={current.questions}
                  busy={acting}
                  detailsOpen={open.has(row.id)}
                  onDetailsOpen={(isOpen) =>
                    setOpen((prev) => {
                      const next = new Set(prev);
                      if (isOpen) next.add(row.id);
                      else next.delete(row.id);
                      return next;
                    })
                  }
                  onMeasure={() => void act(() => api.measureDependencies(current.plan_id, row.id))}
                  onViewFix={onViewFix}
                />
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
