import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, type CheckRow, type ChecksView, type PlanView } from "../api";
import { CheckPanel } from "./checks/CheckPanel";
import { CheckTable } from "./checks/CheckTable";
import { FilterSelect, GroupSection, PageHeader, SearchInput, TableWithPanel, Toolbar } from "./layout";
import { AlsoChecks } from "./checks/CheckPanel";
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
    return () => {
      live = false;
    };
  }, [planId, planStamp, tick]);

  // Live: ask again every second while any check waits or runs.
  useEffect(() => {
    if (!view?.busy) return;
    const timer = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [view]);

  const needle = search.trim().toLowerCase();
  const results = useMemo(() => {
    const labels = new Set<string>();
    for (const g of view?.groups ?? []) for (const r of g.rows) if (r.result) labels.add(r.result.label);
    return Array.from(labels);
  }, [view]);
  const every = useMemo(() => (view?.groups ?? []).flatMap((g) => g.rows), [view]);
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
                  {showPlan ? <TestsScreen importId={importId} plan={plan} onPlan={onPlan} embedded /> : null}
                  {rows.length > 0 ? (
                    <div className={showPlan ? "mt-4" : ""}>
                      {showPlan ? <h3 className="mb-2 text-sm font-semibold text-slate-200">Retests, fix proofs and tries</h3> : null}
                      <CheckTable label={`${g.label} checks`} rows={rows} selectedId={openId} onOpen={(r) => setOpenId(r.id === openId ? null : r.id)} />
                    </div>
                  ) : g.rows.length > 0 && g.key !== "encryption" ? (
                    <p className="px-1 py-2 text-sm text-slate-400">No check matches this search.</p>
                  ) : null}
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
