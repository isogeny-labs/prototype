import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { api, errorMessage, type PlanView, type TestCard } from "../api";
import { CLOSED_SENTENCE, useReadOnly } from "../readOnly";
import {
  DemoDataLabel,
  ErrorBox,
  NotTestedBox,
  PrimaryButton,
  ResultBadge,
  RichTextView,
  SecondaryButton,
  SourceTag,
  StatusView,
  splitByGroup,
  useDismiss,
} from "./ui";
import { PageHeader, usePanelOpen } from "./layout";
import { ItemLinkView } from "./related";

const POLL_MS = 1000;

/** The order after moving one card to the place of another. */
function moved(order: number[], id: number, toIndex: number): number[] {
  const from = order.indexOf(id);
  if (from < 0 || toIndex < 0 || toIndex >= order.length || from === toIndex)
    return order;
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
  headingLevel = 2,
  compact = false,
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
  onDragOver: (e: DragEvent<HTMLTableRowElement>) => void;
  onDrop: (e: DragEvent<HTMLTableRowElement>) => void;
  onDragEnd: () => void;
  handleRef: (el: HTMLButtonElement | null) => void;
  /** 2 in the flat list; 3 when the card sits under a group heading. */
  headingLevel?: 2 | 3;
  /** Phase 5b: beside an open detail panel, the row stacks instead of squeezing its columns. */
  compact?: boolean;
}) {
  const Heading = headingLevel === 3 ? "h3" : "h2";
  // A closed assessment is read-only: every control that changes the plan turns off and says why.
  const closed = useReadOnly();
  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      onMoveBy(-1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      onMoveBy(1);
    }
  }

  const handle = (
    <button
      type="button"
      ref={handleRef}
      data-testid="drag-handle"
      draggable={!closed}
      disabled={closed}
      title={closed ? CLOSED_SENTENCE : "Drag to reorder"}
      aria-label={`Reorder ${card.title}, position ${position} of ${total}. Drag, or press the up or down arrow key.`}
      onKeyDown={onKeyDown}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className="grid w-7 shrink-0 cursor-grab grid-cols-[4px_4px] justify-center gap-1 rounded-md border border-slate-700 py-2 hover:border-slate-500 active:cursor-grabbing"
    >
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <span key={i} aria-hidden="true" className="h-1 w-1 rounded-full bg-slate-400" />
      ))}
    </button>
  );
  const title = (
    <Heading className="text-[15px] font-semibold text-slate-100">
      {card.title}
      {card.tag ? (
        <>
          {" "}
          <SourceTag>{card.tag}</SourceTag>
        </>
      ) : null}
    </Heading>
  );
  const status =
    card.status === "done" && card.result ? (
      <span className="flex flex-col items-start gap-1">
        <ResultBadge label={card.result.label} tone={card.result.tone} />
        {/* Phase 5b: a finished test opens its result on Evidence (its record, every run, Related). */}
        <ItemLinkView link={{ page: "evidence", item: `test-${card.id}` }} testId="see-the-evidence" className="text-xs text-sky-300 hover:underline">
          See the evidence
        </ItemLinkView>
      </span>
    ) : (
      <StatusView status={card} />
    );
  const run = (
    <button
      type="button"
      aria-label={`Run ${card.title}`}
      disabled={closed || locked || !card.can_run}
      title={closed ? CLOSED_SENTENCE : undefined}
      onClick={onRun}
      className="rounded-lg border border-slate-600 px-3.5 py-1.5 text-sm font-medium text-slate-100 transition-colors hover:border-slate-400 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
    >
      Run
    </button>
  );
  const remove = (
    <button
      type="button"
      aria-label={`Remove ${card.title}`}
      title={closed ? CLOSED_SENTENCE : "Remove from the plan"}
      disabled={closed || locked || !card.can_remove}
      onClick={onRemove}
      className="flex h-[30px] w-[30px] items-center justify-center rounded-md border border-slate-700 text-base text-slate-300 hover:border-slate-500 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span aria-hidden="true">×</span>
    </button>
  );
  const rowClass = `border-b border-slate-800/70 last:border-b-0 ${
    dropTarget ? "bg-sky-400/[0.07] shadow-[inset_2px_0_0_var(--color-sky-400)]" : ""
  } ${dragging ? "opacity-50" : ""}`;

  // Phase 5c: an advisory check says which advisory it came from, with the way to it. The words are the backend's.
  const advisory = card.advisory ? (
    <p className="mt-1 text-xs">
      <ItemLinkView link={card.advisory.link} testId="card-advisory" className="text-sky-300 hover:underline">
        {card.advisory.label}
      </ItemLinkView>
    </p>
  ) : null;

  if (compact) {
    // Phase 5b: beside an open panel, a row stacks: the handle and the name, then its status, Run and the ×.
    return (
      <tr data-testid="test-card" data-kind={card.kind} data-status={card.status} onDragOver={onDragOver} onDrop={onDrop} className={rowClass}>
        <td colSpan={5} className="px-3 py-2.5 align-top">
          <div className="flex items-start gap-2">
            {handle}
            <div className="min-w-0 flex-1">
              {title}
              {advisory}
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <span data-testid="test-status">{status}</span>
                <span className="ml-auto flex items-center gap-2">
                  {run}
                  {remove}
                </span>
              </div>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr data-testid="test-card" data-kind={card.kind} data-status={card.status} onDragOver={onDragOver} onDrop={onDrop} className={rowClass}>
      <td className="w-12 px-4 py-3 align-top">{handle}</td>
      <td className="min-w-0 px-4 py-3 align-top">
        {title}
        <p className="mt-1 text-sm text-slate-300">{card.description}</p>
        <p className="mt-1 text-[13px] text-slate-400">{card.why}</p>
        {advisory}
      </td>
      <td data-testid="test-status" className="w-56 px-4 py-3 align-top">
        {status}
      </td>
      <td className="w-px whitespace-nowrap px-4 py-3 align-top">{run}</td>
      <td className="w-px px-4 py-3 align-top">{remove}</td>
    </tr>
  );
}

interface Props {
  importId: number;
  /** The plan as last seen, so coming back to this step doesn't flash empty. */
  plan: PlanView | null;
  onPlan: (plan: PlanView) => void;
  /** Phase 5b: drawn inside Checks, under Encryption tests, as "Test plan" (every button and rule as before). */
  embedded?: boolean;
}

export function TestsScreen({ importId, plan, onPlan, embedded = false }: Props) {
  // Phase 5b: inside Checks, a check's panel can be open beside the plan; then each row stacks.
  const compact = usePanelOpen();
  const readOnly = useReadOnly();
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

  // Opening the step asks for the plan, so its buttons and statuses are as they are now (a proof running, a test
  // running). The first time this proposes and locks the suggested tests; afterwards it answers with the same plan.
  // Phase 5b: inside Checks the app has already made it (when the file came in), so it is only read again.
  const known = embedded && plan !== null && plan.import_id === importId;
  useEffect(() => {
    let live = true;
    (known ? api.getPlan(importId) : api.ensurePlan(importId))
      .then((next) => {
        if (live && next) onPlan(next);
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

  // With one server and one signing program the list is flat: one section with no heading. When the plan is
  // grouped, each group is a section, and a card only moves inside its own section.
  const headings = new Map(current.groups.map((g) => [g.key, g]));
  const sections = current.grouped
    ? splitByGroup(current.groups, current.tests, (t) => t.group)
    : [{ key: null, items: current.tests }];
  const sectionOf = new Map<number, number>();
  sections.forEach((section, i) =>
    section.items.forEach((t) => sectionOf.set(t.id, i)),
  );

  /** Moves a card to a place inside its own section, and sends the whole list in the order shown. */
  function reorder(id: number, toIndex: number) {
    const at = sectionOf.get(id);
    if (at === undefined) return;
    const scope = sections[at]!.items.map((t) => t.id);
    const nextScope = moved(scope, id, toIndex);
    if (nextScope === scope) return;
    const next = sections.flatMap((section, i) =>
      i === at ? nextScope : section.items.map((t) => t.id),
    );
    const card = current.tests.find((t) => t.id === id);
    // Show the new order straight away; the server's answer then replaces it.
    const byId = new Map(current.tests.map((t) => [t.id, t]));
    onPlan({ ...current, tests: next.flatMap((x) => byId.get(x) ?? []) });
    const sectionKey = sections[at]!.key;
    const heading =
      sectionKey !== null ? headings.get(sectionKey)?.heading : undefined;
    if (card) {
      setAnnounce(
        heading
          ? `${card.title} moved to position ${toIndex + 1} of ${scope.length} under ${heading}.`
          : `${card.title} moved to position ${toIndex + 1} of ${scope.length}.`,
      );
    }
    void act(() => api.reorder(current.id, next));
  }

  const dragSection = dragId !== null ? sectionOf.get(dragId) : undefined;

  function renderCards(
    items: TestCard[],
    sectionIndex: number,
    headingLevel: 2 | 3,
  ) {
    return items.map((card, index) => (
      <Card
        key={card.id}
        card={card}
        position={index + 1}
        total={items.length}
        headingLevel={headingLevel}
        compact={compact}
        locked={busy}
        dragging={dragId === card.id}
        dropTarget={
          dragId !== null &&
          dragId !== card.id &&
          overId === card.id &&
          dragSection === sectionIndex
        }
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
          const li = e.currentTarget.closest("tr");
          if (li && typeof e.dataTransfer.setDragImage === "function")
            e.dataTransfer.setDragImage(li, 20, 20);
        }}
        onDragOver={(e) => {
          // A card can't be dropped into another group: no drop is offered there.
          if (dragId === null || dragSection !== sectionIndex) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
          if (overId !== card.id) setOverId(card.id);
        }}
        onDrop={(e) => {
          if (dragId === null || dragSection !== sectionIndex) return;
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
    ));
  }

  const cardTable = (rowsOfCards: ReactNode, label: string) => (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/30">
      <table
        aria-label={label}
        className="w-full border-collapse text-left text-sm"
      >
        <thead>
          {compact ? (
            <tr className="border-b border-slate-800 text-xs font-medium uppercase tracking-wider text-slate-500">
              <th scope="col" colSpan={5} className="px-3 py-2.5 font-medium">
                Test
              </th>
            </tr>
          ) : (
          <tr className="border-b border-slate-800 text-xs font-medium uppercase tracking-wider text-slate-500">
            <th scope="col" className="px-4 py-2.5 font-medium">
              <span className="sr-only">Reorder</span>
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Test
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Status
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              <span className="sr-only">Run</span>
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              <span className="sr-only">Remove</span>
            </th>
          </tr>
          )}
        </thead>
        <tbody>{rowsOfCards}</tbody>
      </table>
    </div>
  );

  return (
    <section aria-label={embedded ? "Test plan" : "Tests"} data-testid="test-plan">
      {embedded ? (
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 max-w-3xl">
            {current.is_demo ? <DemoDataLabel /> : null}
            <h3 className="mt-1 text-base font-semibold text-slate-100">Test plan</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-400">{current.intro}</p>
          </div>
          <PrimaryButton disabled={busy || !current.can_run_all} onClick={() => void act(() => api.runAll(current.id))}>
            Run all
          </PrimaryButton>
        </div>
      ) : (
        <PageHeader
          eyebrow={current.is_demo ? <DemoDataLabel /> : undefined}
          title="Tests"
          description={current.intro}
          actions={
            <PrimaryButton
              disabled={busy || !current.can_run_all}
              onClick={() => void act(() => api.runAll(current.id))}
            >
              Run all
            </PrimaryButton>
          }
        />
      )}

      <p data-testid="plan-subject" className="-mt-2 text-sm text-slate-400">
        <RichTextView parts={current.subject} />
      </p>

      {current.not_tested ? (
        <div className="mt-4">
          <NotTestedBox
            title={current.not_tested.title}
            items={current.not_tested.items}
          />
        </div>
      ) : null}

      {error ? (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      {current.tests.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">
          There are no tests in the plan.
        </p>
      ) : current.grouped ? (
        <div className="mt-6 flex flex-col gap-6">
          {sections.map((section, i) => {
            const group =
              section.key !== null ? headings.get(section.key) : undefined;
            return (
              <section
                key={section.key ?? `rest-${i}`}
                data-testid="test-group"
                data-group={section.key ?? ""}
              >
                {group ? (
                  <>
                    <h2 className="text-base font-semibold text-slate-100">
                      {group.heading}
                    </h2>
                    {group.note ? (
                      <p
                        data-testid="test-group-note"
                        className="mt-0.5 text-[13px] text-slate-400"
                      >
                        {group.note}
                      </p>
                    ) : null}
                  </>
                ) : null}
                <div className="mt-3">
                  {cardTable(
                    renderCards(section.items, i, group ? 3 : 2),
                    group?.heading ?? "Tests",
                  )}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div className="mt-6">
          {cardTable(renderCards(current.tests, 0, 2), "Tests")}
        </div>
      )}

      {/* SPEC section 11: every screen that shows a result carries this one line. */}
      <p
        data-testid="disclaimer"
        className="mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300"
      >
        Passing these tests doesn't prove a system secure. It shows these
        specific checks passed.
      </p>

      <div ref={menuRef} className="relative mt-4">
        <SecondaryButton
          expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          + Add test
        </SecondaryButton>
        {menuOpen ? (
          <div
            role="menu"
            aria-label={current.catalog_title}
            className="absolute left-0 top-11 z-10 w-[470px] max-w-[calc(100vw-2rem)] rounded-[10px] border border-slate-600 bg-slate-900 p-1.5 shadow-2xl shadow-black/60"
          >
            <p className="px-2.5 pb-1.5 pt-2 text-xs text-slate-400">
              {current.catalog_title}
            </p>
            {current.catalog.length === 0 ? (
              <p className="px-2.5 py-2 text-[13px] text-slate-300">
                Every test in the catalog is already in the plan.
              </p>
            ) : (
              current.catalog.map((item) => (
                <button
                  key={item.catalog_id}
                  type="button"
                  role="menuitem"
                  disabled={busy || readOnly}
                  title={readOnly ? CLOSED_SENTENCE : undefined}
                  onClick={() => {
                    setMenuOpen(false);
                    void act(() => api.addTest(current.id, item.catalog_id));
                  }}
                  className="block w-full rounded-md p-2.5 text-left hover:bg-slate-800 focus-visible:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="text-sm font-semibold text-slate-100">
                    {item.title}
                  </span>
                  {item.tag ? (
                    <>
                      {" "}
                      <SourceTag>{item.tag}</SourceTag>
                    </>
                  ) : null}
                  <span className="mt-0.5 block text-[13px] text-slate-400">
                    {item.description}
                  </span>
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
