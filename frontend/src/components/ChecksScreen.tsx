import { useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePanelStamp } from "../changes";
import {
  api,
  errorMessage,
  type CheckGroup,
  type CheckRow,
  type ChecksView,
  type LabView,
  type PlanView,
} from "../api";
import { CheckPanel } from "./checks/CheckPanel";
import { CheckTable } from "./checks/CheckTable";
import {
  BlockSection,
  FilterSelect,
  GroupSection,
  GroupTabs,
  tabTotal,
  ItemPageContext,
  PageHeader,
  PartSection,
  SearchInput,
  TableWithPanel,
  Toolbar,
  useGroupTab,
  useShowGroups,
  type GroupNav,
} from "./layout";
import { AlsoChecks } from "./checks/CheckPanel";
import { RetestMenu, RetestStatus } from "./lab/RetestMenu";
import { ItemLinkView } from "./related";
import { TestsScreen } from "./TestsScreen";
import { ErrorBox } from "./ui";

const POLL_MS = 1000;

interface Props {
  importId: number;
  plan: PlanView | null;
  onPlan: (plan: PlanView) => void;
  /** A check to open (from a link: #/a/<id>/checks?item=<check id>). */
  openItem?: string | null;
  /** The work group whose tab to open (from the address: the Overview, the sidebar, Continue to checks). */
  group?: string | null;
  /** Phase 6b: the Result and Came from filters the address names, and how a change of either goes back into it. A filter
   * changed here also names the open tab, so the tab stays where it is. */
  result?: string | null;
  from?: string | null;
  onFilters?: (filters: { result?: string | null; from?: string | null; group?: string | null }) => void;
  /** A tab chosen here: it goes into the address. */
  onGroup?: (group: string) => void;
  /** The open tab and the groups, for the sidebar. */
  onGroupShown?: (nav: GroupNav) => void;
}

/** Phase 5b: Checks (was Tests). Every check in the assessment, wherever it was started, in the four work groups. The
 * test plan sits under Crypto tests with every button it had; every other check is started where it is today. Since 20
 * November 2026 the groups are tabs: one group's table at a time. */
/** The test plan is drawn once and then moved, never drawn again: by itself while the list of checks is being read,
 * then inside its part. So what a person opened in it meanwhile (the + Add test menu, a card being dragged) stays as it
 * is, however long the list takes. `host` goes on the place the plan belongs in; the plan is drawn only while such a
 * place is on the page (a folded part, or a filter that leaves the plan out, draws none). */
function usePlanHolder() {
  const [holder] = useState<HTMLElement | null>(() => {
    if (typeof document === "undefined") return null;
    const el = document.createElement("div");
    el.className = "contents";
    return el;
  });
  const [hosted, setHosted] = useState(false);
  const focused = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!holder) return;
    const onIn = (e: FocusEvent) => {
      focused.current = e.target instanceof HTMLElement ? e.target : null;
    };
    const onOut = (e: FocusEvent) => {
      if (e.relatedTarget) focused.current = null; // the person moved on to something else
    };
    holder.addEventListener("focusin", onIn);
    holder.addEventListener("focusout", onOut);
    return () => {
      holder.removeEventListener("focusin", onIn);
      holder.removeEventListener("focusout", onOut);
    };
  }, [holder]);
  const host = useCallback(
    (el: HTMLElement | null) => {
      setHosted(el !== null);
      if (!el || !holder || holder.parentElement === el) return;
      el.appendChild(holder);
      // Moving it takes the keyboard's place away. Give it back, unless the person is somewhere else by now.
      const was = focused.current;
      if (
        was &&
        holder.contains(was) &&
        (document.activeElement === null || document.activeElement === document.body)
      ) {
        was.focus({ preventScroll: true });
      }
    },
    [holder],
  );
  return { holder, hosted, host };
}

export function ChecksScreen({
  importId,
  plan,
  onPlan,
  openItem = null,
  group = null,
  result = null,
  from = null,
  onFilters,
  onGroup,
  onGroupShown,
}: Props) {
  const planHolder = usePlanHolder();
  const tabIds = useId();
  const [view, setView] = useState<ChecksView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [fromFilter, setFromFilterState] = useState(from ?? "all");
  const [resultFilter, setResultFilterState] = useState(result ?? "all");
  // (the address names these two filters: a change made here goes into it, and one made there comes back here)
  const setFromFilter = (value: string) => {
    setFromFilterState(value);
    onFilters?.({ from: value === "all" ? null : value, group: active });
  };
  const setResultFilter = (value: string) => {
    setResultFilterState(value);
    onFilters?.({ result: value === "all" ? null : value, group: active });
  };
  const [openId, setOpenId] = useState<string | null>(openItem);
  // The 5c fixes: a part, and a block inside it, folds too. A block that is not the newest starts folded.
  const [partFolded, setPartFolded] = useState<Record<string, boolean>>({});
  const [blockOpen, setBlockOpen] = useState<Record<string, boolean>>({});
  // Retest new version is the button Evidence has: its menu, its rules and its reasons come from the same view.
  const [lab, setLab] = useState<LabView | null>(null);
  const [retesting, setRetesting] = useState(false);
  const [tick, setTick] = useState(0);
  // Phase 6a: a decision or a start sent from the Otto panel: this page reads its view again.
  const panelStamp = usePanelStamp();
  const planId = plan?.id ?? null;
  const planStamp = plan ? `${plan.running}:${plan.tests.map((t) => `${t.id}${t.status}`).join(",")}` : "";

  useEffect(() => setOpenId(openItem), [openItem]);
  useEffect(() => setFromFilterState(from ?? "all"), [from]);
  useEffect(() => setResultFilterState(result ?? "all"), [result]);

  useEffect(() => {
    if (planId === null) return;
    let live = true;
    api
      .getChecks(planId)
      .then((v) => {
        if (live) {
          setView(v);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    // (if this read fails the checks still show; only the Retest button is missing until the next read)
    api
      .getLab(planId)
      .then((v) => {
        if (live) setLab(v);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [planId, planStamp, tick, panelStamp]);

  // Live: ask again every second while any check waits or runs (a retest started here, on Evidence or in Fixes too).
  const live = Boolean(view?.busy) || Boolean(lab?.retest.running);
  useEffect(() => {
    if (!live) return;
    const timer = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [live, view, lab]);

  const needle = search.trim().toLowerCase();
  const results = useMemo(() => {
    const labels = new Set<string>();
    for (const g of view?.groups ?? []) for (const r of g.rows) if (r.result) labels.add(r.result.label);
    return Array.from(labels);
  }, [view]);
  // Every row that can be opened: the groups' own rows, and the rows of each retest's and each proof's block.
  const every = useMemo(
    () =>
      (view?.groups ?? []).flatMap((g) => [
        ...(g.parts
          ? [...g.parts.retests.blocks, ...g.parts.proofs.blocks, ...(g.parts.changes?.blocks ?? [])].flatMap(
              (b) => b.rows,
            )
          : []),
        ...g.rows,
      ]),
    [view],
  );
  const opened = every.find((r) => r.id === openId) ?? null;

  function fits(r: CheckRow): boolean {
    if (fromFilter !== "all" && r.came_from.key !== fromFilter) return false;
    if (resultFilter !== "all" && r.result?.label !== resultFilter) return false;
    if (!needle) return true;
    return [r.name, r.ran_on, r.came_from.label, r.result?.label ?? ""].some((t) => t.toLowerCase().includes(needle));
  }
  function keep(r: CheckRow): boolean {
    return r.id === openId || fits(r); // the open check stays listed whatever the search
  }

  // 20 November 2026: the rows a group's tab lists. Crypto tests lists its test plan's tests (as the plan's cards) and
  // the rows of its parts; a check sits in one group, so a row is counted in one tab only.
  const tabRows = (g: CheckGroup): CheckRow[] =>
    g.key === "encryption"
      ? [
          ...g.rows.filter((r) => r.id.startsWith("test-")),
          ...(g.parts
            ? [...g.parts.retests.blocks, ...g.parts.proofs.blocks, ...(g.parts.changes?.blocks ?? [])]
                .flatMap((b) => b.rows)
                .concat(g.parts.tries?.rows ?? [])
            : g.rows.filter((r) => !r.id.startsWith("test-"))),
        ]
      : g.rows;
  const groupKeys = useMemo(() => (view?.groups ?? []).map((g) => g.key), [view]);
  // Which tab to open: the one the address names; else the tab of the check the address names; else, with a filter in
  // the address, the first tab with a match; else the first group with something in it (Crypto tests always holds the
  // test plan).
  const [active, choose] = useGroupTab({
    keys: groupKeys,
    group,
    item: openItem,
    filters: `${result ?? ""}\u0000${from ?? ""}`,
    onGroup,
    pick: () => {
      if (!view) return null;
      if (openItem) {
        const holder = view.groups.find((g) =>
          [...g.rows, ...tabRows(g)].some((r) => r.id === openItem || (r.alias != null && r.alias === openItem)),
        );
        if (holder) return holder.key;
      }
      // (the address's own filters: a pick happens when the address changes, before the page's filters follow it)
      if (from || result) {
        const named = (r: CheckRow) => (!from || r.came_from.key === from) && (!result || r.result?.label === result);
        const match = view.groups.find((g) => tabRows(g).some(named));
        if (match) return match.key;
      }
      return (view.groups.find((g) => g.key === "encryption" || g.rows.length > 0) ?? view.groups[0])?.key ?? null;
    },
  });
  useShowGroups(onGroupShown, active, view?.groups ?? null);
  // A check belongs to the tab it sits in: when another tab opens (on the page, from the sidebar, by Back), the panel of a
  // check of another tab closes. Not on an item's own page, which is the panel itself.
  const asPage = Boolean(useContext(ItemPageContext)?.asPage);
  useEffect(() => {
    if (asPage || !view || active === null || openId === null) return;
    const holder = view.groups.find((g) =>
      [...g.rows, ...tabRows(g)].some((r) => r.id === openId || (r.alias != null && r.alias === openId)),
    );
    if (holder && holder.key !== active) setOpenId(null);
    // (only when the tab changes: a check opened from a link opens its own tab with it)
  }, [active]);
  // While a search or a filter is on, each tab says how many of its rows match.
  const narrowedAny = needle !== "" || fromFilter !== "all" || resultFilter !== "all";
  const matches = useMemo(
    () =>
      narrowedAny && view ? Object.fromEntries(view.groups.map((g) => [g.key, tabRows(g).filter(fits).length])) : null,
    // (`fits` reads the search and the two filters named here)
    [narrowedAny, view, needle, fromFilter, resultFilter],
  );

  // Every tab says how many checks it holds and how many of them are findings, counted from the rows of that tab.
  const totals = useMemo(
    () =>
      view ? Object.fromEntries(view.groups.map((g) => [g.key, tabTotal(tabRows(g).map((r) => r.result))])) : null,
    [view],
  );

  // Phase 6b: with the Result filter on, the test plan lists only its tests that read that way ("show me failed
  // checks" lists the failed checks and nothing else). A test of the plan is its row "test-<id>" in the list.
  const planOnly = useMemo(() => {
    if (resultFilter === "all" || !view) return null;
    const ids = new Set<number>();
    for (const g of view.groups)
      for (const r of g.rows)
        if (r.id.startsWith("test-") && r.result?.label === resultFilter) ids.add(Number(r.id.slice(5)));
    return ids;
  }, [view, resultFilter]);
  // (the first thing in the page in both of its states below, so it is the same drawing before and after the list arrives)
  const thePlan =
    planHolder.holder && planHolder.hosted
      ? createPortal(
          <TestsScreen
            importId={importId}
            plan={plan}
            onPlan={onPlan}
            embedded
            only={planOnly}
            onlyLabel={planOnly ? resultFilter : undefined}
          />,
          planHolder.holder,
        )
      : null;
  const planPlace = <div ref={planHolder.host} data-testid="test-plan-place" className="contents" />;

  if (!view || planId === null) {
    return (
      <section aria-label="Checks">
        {thePlan}
        <PageHeader title="Checks" description="Every check in this assessment, wherever it was started." />
        {error ? <ErrorBox>{error}</ErrorBox> : <p className="text-sm text-slate-400">Loading…</p>}
        {/* The test plan is there at once when the address opens Crypto tests (Continue to checks, a link to the plan), so
            its buttons never wait for the list. */}
        {group === "encryption" ? planPlace : null}
      </section>
    );
  }

  const groups = view.groups.filter((g) => g.key === active);
  const toggleOpen = (r: CheckRow) =>
    setOpenId(r.id === openId || (r.alias != null && r.alias === openId) ? null : r.id);

  /** The 5c fixes: Crypto tests in four labelled parts. Each run shows in one part only. */
  function encryptionParts(g: CheckGroup) {
    const parts = g.parts!;
    type Part = NonNullable<CheckGroup["parts"]>["retests"];
    // "Came from" picks a part by what the part is, and also by its rows: a retest's newest run can have come right
    // after an Apply or a Roll back, and "After Apply" must find it in its block.
    const holds = (part: Part) =>
      [...part.rows, ...part.blocks.flatMap((b) => b.rows)].some((r) => r.came_from.key === fromFilter);
    const wanted = (origin: string, part?: Part) =>
      fromFilter === "all" || fromFilter === origin || (part ? holds(part) : false);
    // (with any filter on, a block that holds a match is open, and one that holds none is left out: it would say that
    // nothing has finished in it)
    const narrowed = needle !== "" || resultFilter !== "all" || fromFilter !== "all";
    const isOpen = (key: string) => !partFolded[key];
    const toggle = (key: string) => setPartFolded((f) => ({ ...f, [key]: !f[key] }));
    const blocks = (part: Part) =>
      part.blocks.map((b) => {
        const rows = b.rows.filter(keep);
        if (narrowed && rows.length === 0) return null;
        // the newest block is open; an older one opens when it is asked for, or when it holds the open row or a match
        const shown = blockOpen[b.key] ?? (b.newest || narrowed || b.rows.some((r) => r.id === openId));
        return (
          <BlockSection
            key={b.key}
            block={b}
            open={shown}
            onToggle={() => setBlockOpen((o) => ({ ...o, [b.key]: !shown }))}
          >
            {rows.length > 0 ? (
              <CheckTable label={`${part.label}: ${b.title}`} rows={rows} selectedId={openId} onOpen={toggleOpen} />
            ) : (
              <p className="px-1 py-1 text-sm text-slate-400">Nothing has finished in this block yet.</p>
            )}
          </BlockSection>
        );
      });
    const tries = parts.tries ? parts.tries.rows.filter(keep) : [];
    return (
      <div data-testid="encryption-parts">
        {/* (with the Result filter on, the part stays even when none of its tests fits: it then says so in one line, and
            + Add test and Run all stay where they are) */}
        {wanted("plan") ? (
          <PartSection part={parts.plan} open={isOpen("plan")} onToggle={() => toggle("plan")}>
            {planPlace}
          </PartSection>
        ) : null}
        {wanted("retest", parts.retests) ? (
          <PartSection
            part={parts.retests}
            open={isOpen("retests")}
            onToggle={() => toggle("retests")}
            actions={
              lab && planId !== null ? (
                <RetestMenu
                  retest={lab.retest}
                  disabled={retesting}
                  onChoose={(v) => {
                    setRetesting(true);
                    setError(null);
                    api
                      .retest(planId, v.version, v.component)
                      .then((next) => {
                        setLab(next);
                        setTick((n) => n + 1);
                        // The plan above is the app's copy from before the retest: read it again, so Run, Run all and ×
                        // turn off with the reason now, not when the server refuses a click.
                        void api
                          .getPlan(importId)
                          .then((fresh) => fresh && onPlan(fresh))
                          .catch(() => undefined);
                      })
                      .catch((e: unknown) => setError(errorMessage(e)))
                      .finally(() => setRetesting(false));
                  }}
                />
              ) : null
            }
          >
            {lab ? <RetestStatus retest={lab.retest} /> : null}
            {blocks(parts.retests)}
          </PartSection>
        ) : null}
        {wanted("proof", parts.proofs) ? (
          <PartSection part={parts.proofs} open={isOpen("proofs")} onToggle={() => toggle("proofs")}>
            {blocks(parts.proofs)}
          </PartSection>
        ) : null}
        {parts.tries && wanted("try", parts.tries) ? (
          <PartSection part={parts.tries} open={isOpen("tries")} onToggle={() => toggle("tries")}>
            {tries.length > 0 ? (
              <CheckTable label={parts.tries.label} rows={tries} selectedId={openId} onOpen={toggleOpen} />
            ) : (
              <p className="px-1 py-1 text-sm text-slate-400">No check matches this search.</p>
            )}
          </PartSection>
        ) : null}
        {/* Phase 6d: the runs of the tests picked for a developer's change, one block for each run. Only once one has run. */}
        {parts.changes && wanted("watch", parts.changes) ? (
          <PartSection part={parts.changes} open={isOpen("changes")} onToggle={() => toggle("changes")}>
            {blocks(parts.changes)}
          </PartSection>
        ) : null}
      </div>
    );
  }

  return (
    <section aria-label="Checks">
      {thePlan}
      <PageHeader title="Checks" description={view.subline} />
      {active !== null ? (
        <GroupTabs
          groups={view.groups}
          active={active}
          onChoose={choose}
          idBase={tabIds}
          matches={matches}
          totals={totals}
        />
      ) : null}
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search checks" placeholder="Search checks" />
        <FilterSelect
          label="Came from"
          value={fromFilter}
          options={[
            { value: "all", label: "Anywhere" },
            ...view.came_from_options.map((o) => ({ value: o.key, label: o.label })),
          ]}
          onChange={setFromFilter}
        />
        <FilterSelect
          label="Result"
          value={resultFilter}
          // (a value from the address that no row reads now is still an option: the control shows the filter that is on)
          options={[
            { value: "all", label: "All results" },
            ...Array.from(new Set([...results, ...(resultFilter !== "all" ? [resultFilter] : [])])).map((r) => ({
              value: r,
              label: r,
            })),
          ]}
          onChange={setResultFilter}
        />
      </Toolbar>
      {error ? <ErrorBox>{error}</ErrorBox> : null}
      <TableWithPanel
        panelOpen={opened !== null}
        table={
          <div>
            {groups.map((g) => {
              // A test of the plan shows as its card (even when its newest run came right after an Apply); never twice.
              const rows = g.rows
                .filter((r) =>
                  g.key === "encryption" ? r.came_from.key !== "plan" && !r.id.startsWith("test-") : true,
                )
                .filter(keep);
              const showPlan = g.key === "encryption" && (fromFilter === "all" || fromFilter === "plan");
              return (
                <GroupSection
                  key={g.key}
                  group={g}
                  counts={g.counts}
                  tabbed={{ idBase: tabIds }}
                  note={g.note}
                  also={<AlsoChecks items={g.also ?? []} which="link" />}
                  emptyText={g.key === "encryption" ? null : g.rows.length === 0 ? g.empty_text : null}
                  startedOn={
                    g.started_on.page === "checks" ? (
                      <span>{g.started_on.label}</span>
                    ) : (
                      <ItemLinkView link={{ page: g.started_on.page, item: null }}>{g.started_on.label}</ItemLinkView>
                    )
                  }
                >
                  {g.key === "encryption" && g.parts ? (
                    encryptionParts(g)
                  ) : (
                    <>
                      {showPlan ? planPlace : null}
                      {rows.length > 0 ? (
                        <div className={showPlan ? "mt-4" : ""}>
                          <CheckTable label={`${g.label} checks`} rows={rows} selectedId={openId} onOpen={toggleOpen} />
                        </div>
                      ) : g.rows.length > 0 && g.key !== "encryption" ? (
                        <p className="px-1 py-2 text-sm text-slate-400">No check matches this search.</p>
                      ) : null}
                    </>
                  )}
                </GroupSection>
              );
            })}
          </div>
        }
        panel={<CheckPanel planId={planId} check={opened} onClose={() => setOpenId(null)} />}
      />
    </section>
  );
}
