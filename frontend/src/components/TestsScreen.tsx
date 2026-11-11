import { useCallback, useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { api, errorMessage, type PlanView, type TestCard } from "../api";
import {
  DemoDataLabel,
  ErrorBox,
  PrimaryButton,
  ResultBadge,
  RichTextView,
  SecondaryButton,
  SourceTag,
  StatusView,
  useDismiss,
} from "./ui";

const POLL_MS = 1000;

/** The order after moving one card to the place of another. */
function moved(order: number[], id: number, toIndex: number): number[] {
  const from = order.indexOf(id);
  if (from < 0 || toIndex < 0 || toIndex >= order.length || from === toIndex) return order;
  const next = order.filter((x) => x !== id);
  next.splice(toIndex, 0, id);
  return next;
}

function Card({
  card,
  position,
  total,
  locked,
  dragging,
  dropTarget,
  onRun,
  onRemove,
  onMoveBy,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  handleRef,
}: {
  card: TestCard;
  position: number;
  total: number;
  locked: boolean;
  dragging: boolean;
  dropTarget: boolean;
  onRun: () => void;
  onRemove: () => void;
  onMoveBy: (delta: number) => void;
  onDragStart: (e: DragEvent<HTMLButtonElement>) => void;
  onDragOver: (e: DragEvent<HTMLLIElement>) => void;
  onDrop: (e: DragEvent<HTMLLIElement>) => void;
  onDragEnd: () => void;
  handleRef: (el: HTMLButtonElement | null) => void;
}) {
  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      onMoveBy(-1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      onMoveBy(1);
    }
  }

  return (
    <li
      data-testid="test-card"
      data-kind={card.kind}
      data-status={card.status}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className={`grid items-center gap-4 rounded-xl border bg-slate-900/40 p-4 md:grid-cols-[28px_1fr_210px_auto_32px] ${
        dropTarget ? "border-sky-400/70" : "border-slate-800"
      } ${dragging ? "opacity-50" : ""}`}
    >
      <button
        type="button"
        ref={handleRef}
        data-testid="drag-handle"
        draggable
        title="Drag to reorder"
        aria-label={`Reorder ${card.title}, position ${position} of ${total}. Drag, or press the up or down arrow key.`}
        onKeyDown={onKeyDown}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        className="grid w-7 cursor-grab grid-cols-[4px_4px] justify-center gap-1 rounded-md border border-slate-700 py-2 hover:border-slate-500 active:cursor-grabbing"
      >
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <span key={i} aria-hidden="true" className="h-1 w-1 rounded-full bg-slate-400" />
        ))}
      </button>

      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-slate-100">
          {card.title}
          {card.tag ? (
            <>
              {" "}
              <SourceTag>{card.tag}</SourceTag>
            </>
          ) : null}
        </h2>
        <p className="mt-1 text-sm text-slate-300">{card.description}</p>
        <p className="mt-1 text-[13px] text-slate-400">{card.why}</p>
      </div>

      <div data-testid="test-status">
        {card.status === "done" && card.result ? (
          <ResultBadge label={card.result.label} tone={card.result.tone} />
        ) : (
          <StatusView status={card} />
        )}
      </div>

      <button
        type="button"
        aria-label={`Run ${card.title}`}
        disabled={locked || !card.can_run}
        onClick={onRun}
        className="rounded-lg border border-slate-600 px-3.5 py-1.5 text-sm font-medium text-slate-100 transition-colors hover:border-slate-400 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Run
      </button>

      <button
        type="button"
        aria-label={`Remove ${card.title}`}
        title="Remove from the plan"
        disabled={locked || !card.can_remove}
        onClick={onRemove}
        className="flex h-[30px] w-[30px] items-center justify-center rounded-md border border-slate-700 text-base text-slate-300 hover:border-slate-500 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span aria-hidden="true">×</span>
      </button>
    </li>
  );
}

interface Props {
  importId: number;
  /** The plan as last seen, so coming back to this step doesn't flash empty. */
  plan: PlanView | null;
  onPlan: (plan: PlanView) => void;
}

export function TestsScreen({ importId, plan, onPlan }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [dragId, setDragId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");
  const [pollTick, setPollTick] = useState(0);
  const handles = useRef(new Map<number, HTMLButtonElement>());
  const focusAfter = useRef<number | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useDismiss(menuOpen, menuRef, closeMenu);

  // Opening the step asks for the plan. The first time this proposes and locks
  // the suggested tests; afterwards it answers with the same plan.
  useEffect(() => {
    let live = true;
    api
      .ensurePlan(importId)
      .then((next) => {
        if (live) onPlan(next);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importId]);

  // Live status: ask again every second while anything is waiting or running.
  const planId = plan?.id ?? null;
  const running = plan?.running ?? false;
  useEffect(() => {
    if (planId === null || !running) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .pollPlan(planId)
        .then((next) => {
          if (!live) return;
          onPlan(next);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, running, pollTick]);

  // Keep the keyboard on the handle that was just moved.
  useEffect(() => {
    if (focusAfter.current === null) return;
    handles.current.get(focusAfter.current)?.focus();
    focusAfter.current = null;
  });

  if (!plan) {
    return (
      <section aria-labelledby="tests-title" className="space-y-4">
        <h1 id="tests-title" className="text-xl font-semibold text-slate-50">
          Tests
        </h1>
        {error ? (
          <ErrorBox title="The test plan couldn't be loaded">{error}</ErrorBox>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </section>
    );
  }

  const current = plan;

  async function act(call: () => Promise<PlanView>) {
    setBusy(true);
    setError(null);
    try {
      onPlan(await call());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function reorder(id: number, toIndex: number) {
    const order = current.tests.map((t) => t.id);
    const next = moved(order, id, toIndex);
    if (next === order) return;
    const card = current.tests.find((t) => t.id === id);
    // Show the new order straight away; the server's answer then replaces it.
    const byId = new Map(current.tests.map((t) => [t.id, t]));
    onPlan({ ...current, tests: next.flatMap((x) => byId.get(x) ?? []) });
    if (card) setAnnounce(`${card.title} moved to position ${toIndex + 1} of ${order.length}.`);
    void act(() => api.reorder(current.id, next));
  }

  return (
    <section aria-labelledby="tests-title">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 id="tests-title" className="text-xl font-semibold text-slate-50">
              Tests
            </h1>
            {current.is_demo ? <DemoDataLabel /> : null}
          </div>
          <p className="mt-1 text-sm text-slate-400">{current.intro}</p>
        </div>
        <PrimaryButton disabled={busy || !current.can_run_all} onClick={() => void act(() => api.runAll(current.id))}>
          Run all
        </PrimaryButton>
      </div>

      <p data-testid="plan-subject" className="mt-3.5 text-sm text-slate-400">
        <RichTextView parts={current.subject} />
      </p>

      {error ? (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      {current.tests.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">There are no tests in the plan.</p>
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {current.tests.map((card, index) => (
            <Card
              key={card.id}
              card={card}
              position={index + 1}
              total={current.tests.length}
              locked={busy}
              dragging={dragId === card.id}
              dropTarget={dragId !== null && dragId !== card.id && overId === card.id}
              handleRef={(el) => {
                if (el) handles.current.set(card.id, el);
                else handles.current.delete(card.id);
              }}
              onRun={() => void act(() => api.runTest(current.id, card.id))}
              onRemove={() => void act(() => api.removeTest(current.id, card.id))}
              onMoveBy={(delta) => {
                focusAfter.current = card.id;
                reorder(card.id, index + delta);
              }}
              onDragStart={(e) => {
                setDragId(card.id);
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", String(card.id));
                const li = e.currentTarget.closest("li");
                if (li && typeof e.dataTransfer.setDragImage === "function") e.dataTransfer.setDragImage(li, 20, 20);
              }}
              onDragOver={(e) => {
                if (dragId === null) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (overId !== card.id) setOverId(card.id);
              }}
              onDrop={(e) => {
                if (dragId === null) return;
                e.preventDefault();
                const id = dragId;
                setDragId(null);
                setOverId(null);
                reorder(id, index);
              }}
              onDragEnd={() => {
                setDragId(null);
                setOverId(null);
              }}
            />
          ))}
        </ul>
      )}

      {/* SPEC section 11: every screen that shows a result carries this one line. */}
      <p data-testid="disclaimer" className="mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        Passing these tests doesn't prove a system secure. It shows these specific checks passed.
      </p>

      <div ref={menuRef} className="relative mt-4">
        <SecondaryButton expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>
          + Add test
        </SecondaryButton>
        {menuOpen ? (
          <div
            role="menu"
            aria-label={current.catalog_title}
            className="absolute left-0 top-11 z-10 w-[470px] max-w-[calc(100vw-2rem)] rounded-[10px] border border-slate-600 bg-slate-900 p-1.5 shadow-2xl shadow-black/60"
          >
            <p className="px-2.5 pb-1.5 pt-2 text-xs text-slate-400">{current.catalog_title}</p>
            {current.catalog.length === 0 ? (
              <p className="px-2.5 py-2 text-[13px] text-slate-300">Every test in the catalog is already in the plan.</p>
            ) : (
              current.catalog.map((item) => (
                <button
                  key={item.catalog_id}
                  type="button"
                  role="menuitem"
                  disabled={busy}
                  onClick={() => {
                    setMenuOpen(false);
                    void act(() => api.addTest(current.id, item.catalog_id));
                  }}
                  className="block w-full rounded-md p-2.5 text-left hover:bg-slate-800 focus-visible:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="text-sm font-semibold text-slate-100">{item.title}</span>
                  {item.tag ? (
                    <>
                      {" "}
                      <SourceTag>{item.tag}</SourceTag>
                    </>
                  ) : null}
                  <span className="mt-0.5 block text-[13px] text-slate-400">{item.description}</span>
                </button>
              ))
            )}
            <p className="mt-1.5 border-t border-slate-800 px-2.5 pb-1 pt-2 text-xs text-slate-400">
              {current.catalog_note}
            </p>
          </div>
        ) : null}
      </div>

      <p aria-live="polite" className="sr-only">
        {announce}
      </p>
    </section>
  );
}
