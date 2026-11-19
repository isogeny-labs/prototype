import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, type CheckGroup, type CheckRow, type ChecksView, type LabView, type PlanView } from "../api";
import { CheckPanel } from "./checks/CheckPanel";
import { CheckTable } from "./checks/CheckTable";
import { BlockSection, FilterSelect, GroupSection, PageHeader, PartSection, SearchInput, TableWithPanel, Toolbar } from "./layout";
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
  /** A work group to filter to (from the Overview). */
  group?: string | null;
}

/** Phase 5b: Checks (was Tests). Every check in the assessment, wherever it was started, in the four work groups. The
 * test plan sits under Encryption tests with every button it had; every other check is started where it is today. */
export function ChecksScreen({ importId, plan, onPlan, openItem = null, group = null }: Props) {
  const [view, setView] = useState<ChecksView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState<string>(group ?? "all");
  const [fromFilter, setFromFilter] = useState("all");
  const [resultFilter, setResultFilter] = useState("all");
  const [openId, setOpenId] = useState<string | null>(openItem);
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  // The 5c fixes: a part, and a block inside it, folds too. A block that is not the newest starts folded.
  const [partFolded, setPartFolded] = useState<Record<string, boolean>>({});
  const [blockOpen, setBlockOpen] = useState<Record<string, boolean>>({});
  // Retest new version is the button Evidence has: its menu, its rules and its reasons come from the same view.
  const [lab, setLab] = useState<LabView | null>(null);
  const [retesting, setRetesting] = useState(false);
  const [tick, setTick] = useState(0);
  const planId = plan?.id ?? null;
  const planStamp = plan ? `${plan.running}:${plan.tests.map((t) => `${t.id}${t.status}`).join(",")}` : "";

  useEffect(() => setOpenId(openItem), [openItem]);
  useEffect(() => setGroupFilter(group ?? "all"), [group]);

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
  }, [planId, planStamp, tick]);

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
        ...(g.parts ? [...g.parts.retests.blocks, ...g.parts.proofs.blocks].flatMap((b) => b.rows) : []),
        ...g.rows,
      ]),
    [view],
  );
  const opened = every.find((r) => r.id === openId) ?? null;

  function keep(r: CheckRow): boolean {
    if (r.id === openId) return true; // the open check stays listed whatever the search
    if (fromFilter !== "all" && r.came_from.key !== fromFilter) return false;
    if (resultFilter !== "all" && r.result?.label !== resultFilter) return false;
    if (!needle) return true;
    return [r.name, r.ran_on, r.came_from.label, r.result?.label ?? ""].some((t) => t.toLowerCase().includes(needle));
  }

  if (!view || planId === null) {
    return (
      <section aria-label="Checks">
        <PageHeader title="Checks" description="Every check in this assessment, wherever it was started." />
        {error ? <ErrorBox>{error}</ErrorBox> : <p className="text-sm text-slate-400">Loading…</p>}
        {/* The test plan is there at once, so its buttons never wait for the list. */}
        <TestsScreen importId={importId} plan={plan} onPlan={onPlan} embedded />
      </section>
    );
  }

  const groups = view.groups.filter((g) => groupFilter === "all" || g.key === groupFilter);
  const toggleOpen = (r: CheckRow) => setOpenId(r.id === openId || (r.alias != null && r.alias === openId) ? null : r.id);

  /** The 5c fixes: Encryption tests in four labelled parts. Each run shows in one part only. */
  function encryptionParts(g: CheckGroup) {
    const parts = g.parts!;
    const wanted = (origin: string) => fromFilter === "all" || fromFilter === origin;
    const filtering = needle !== "" || resultFilter !== "all";
    const isOpen = (key: string) => !partFolded[key];
    const toggle = (key: string) => setPartFolded((f) => ({ ...f, [key]: !f[key] }));
    const blocks = (part: NonNullable<CheckGroup["parts"]>["retests"]) =>
      part.blocks.map((b) => {
        const rows = b.rows.filter(keep);
        if (filtering && rows.length === 0) return null;
        // the newest block is open; an older one opens when it is asked for, or when it holds the open row or a match
        const shown = blockOpen[b.key] ?? (b.newest || filtering || b.rows.some((r) => r.id === openId));
        return (
          <BlockSection key={b.key} block={b} open={shown} onToggle={() => setBlockOpen((o) => ({ ...o, [b.key]: !shown }))}>
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
        {wanted("plan") ? (
          <PartSection part={parts.plan} open={isOpen("plan")} onToggle={() => toggle("plan")}>
            <TestsScreen importId={importId} plan={plan} onPlan={onPlan} embedded />
          </PartSection>
        ) : null}
        {wanted("retest") ? (
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
        {wanted("proof") ? (
          <PartSection part={parts.proofs} open={isOpen("proofs")} onToggle={() => toggle("proofs")}>
            {blocks(parts.proofs)}
          </PartSection>
        ) : null}
        {parts.tries && wanted("try") ? (
          <PartSection part={parts.tries} open={isOpen("tries")} onToggle={() => toggle("tries")}>
            {tries.length > 0 ? (
              <CheckTable label={parts.tries.label} rows={tries} selectedId={openId} onOpen={toggleOpen} />
            ) : (
              <p className="px-1 py-1 text-sm text-slate-400">No check matches this search.</p>
            )}
          </PartSection>
        ) : null}
      </div>
    );
  }

  return (
    <section aria-label="Checks">
      <PageHeader title="Checks" description={view.subline} />
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search checks" placeholder="Search checks" />
        <FilterSelect
          label="Group"
          value={groupFilter}
          options={[{ value: "all", label: "All groups" }, ...view.groups.map((g) => ({ value: g.key, label: g.label }))]}
          onChange={setGroupFilter}
        />
        <FilterSelect
          label="Came from"
          value={fromFilter}
          options={[{ value: "all", label: "Anywhere" }, ...view.came_from_options.map((o) => ({ value: o.key, label: o.label }))]}
          onChange={setFromFilter}
        />
        <FilterSelect
          label="Result"
          value={resultFilter}
          options={[{ value: "all", label: "All results" }, ...results.map((r) => ({ value: r, label: r }))]}
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
                .filter((r) => (g.key === "encryption" ? r.came_from.key !== "plan" && !r.id.startsWith("test-") : true))
                .filter(keep);
              const showPlan = g.key === "encryption" && (fromFilter === "all" || fromFilter === "plan");
              return (
                <GroupSection
                  key={g.key}
                  group={g}
                  counts={g.counts}
                  open={!folded[g.key]}
                  onToggle={() => setFolded((f) => ({ ...f, [g.key]: !f[g.key] }))}
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
                      {showPlan ? <TestsScreen importId={importId} plan={plan} onPlan={onPlan} embedded /> : null}
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
