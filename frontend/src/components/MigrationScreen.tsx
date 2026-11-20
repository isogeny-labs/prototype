import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePanelStamp } from "../changes";
import {
  api,
  ApiError,
  errorMessage,
  type EvidenceExport,
  type MigrationOptionKey,
  type MigrationSettingField,
  type MigrationSystem,
  type MigrationView,
} from "../api";
import { DependenciesView } from "./dependencies/DependenciesView";
import { RelatedFor } from "./related";
import { downloadEvidence } from "./evidenceDownload";
import { Roadmap } from "./migration/Roadmap";
import { SystemDetail } from "./migration/SystemDetail";
import { StatusPill } from "./migration/parts";
import type { SaveChoice } from "./migration/OptionCard";
import { DataTable, DetailPanel, FilterSelect, ItemPageContext, PageHeader, SearchInput, SummaryCards, TableWithPanel, Toolbar, type Column } from "./layout";
import { FromOttoTag, ProposalStatusChip } from "./otto/ProposalCard";
import { DemoDataLabel, ErrorBox, RichTextView, SecondaryButton } from "./ui";

const POLL_MS = 1000;

export type MigrationTab = "systems" | "roadmap" | "dependencies";
type Tab = MigrationTab;

interface Props {
  importId: number;
  /** "View in Fixes": the app opens the Fixes step on that fix. */
  onViewFix: (fixId: string) => void;
  /**
   * Something the plan summary depends on may have changed (the plan was made, a measurement finished, a choice
   * or a setting was saved): the app loads the plan again so the Fixes step opens without a page refresh.
   */
  onPlanChanged: () => void;
  /** Phase 5a: the view the sidebar picked (Systems, Roadmap, Dependencies); the switches still work and tell the app. */
  tab?: Tab;
  onTab?: (tab: Tab) => void;
  /** Phase 5b: a system (or, in Dependencies, a library row) to open, from a link. */
  openItem?: string | null;
}

/** Phase 5c: a system that Otto has a proposal for says so in its row of the Systems table: the tag, and where each
 * proposal stands, both in the view's own words. The decision buttons are in the system's panel. */
function OttoMark({ system }: { system: MigrationSystem }) {
  const proposals = system.otto?.proposals ?? [];
  const first = proposals[0];
  if (!first) return null;
  return (
    <span data-testid="system-otto-mark" className="mt-1.5 flex min-w-0 flex-wrap items-center gap-1">
      <FromOttoTag label={first.label} testId="system-otto-label" />
      {proposals.map((p) => (
        <ProposalStatusChip key={p.id} status={p.status} />
      ))}
    </span>
  );
}

/** The Migration step. Every word, status, number and recommendation comes from the backend. */
export function MigrationScreen({
  importId,
  onViewFix,
  onPlanChanged,
  tab: shownTab,
  onTab,
  openItem = null,
}: Props) {
  const [view, setView] = useState<MigrationView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [ownTab, setOwnTab] = useState<Tab>("systems");
  const tab = shownTab ?? ownTab;
  const setTab = (next: Tab) => (onTab ? onTab(next) : setOwnTab(next));
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  // As before the panel, Systems opens on the first system until the person closes the panel (then it stays closed).
  const [dismissed, setDismissed] = useState(false);
  const asPage = Boolean(useContext(ItemPageContext)?.asPage);
  const closePanel = useCallback(() => {
    setSelectedKey(null);
    setDismissed(true);
  }, []);
  const openSystem = useCallback((key: string) => {
    setSelectedKey(key);
    setDismissed(false);
  }, []);
  // Phase 5b: a link names a system ("server:localhost:8443"): open its panel.
  useEffect(() => {
    if (openItem && (openItem.startsWith("server:") || openItem.startsWith("software:"))) openSystem(openItem);
  }, [openItem, openSystem]);
  const [detailsOpen, setDetailsOpen] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [choosing, setChoosing] = useState<{
    system: string;
    option: MigrationOptionKey;
  } | null>(null);
  const [exported, setExported] = useState<EvidenceExport | null>(null);
  const [pollTick, setPollTick] = useState(0);

  // Kept in a ref so a new callback from the app doesn't restart the effects below.
  const planChanged = useRef(onPlanChanged);
  useEffect(() => {
    planChanged.current = onPlanChanged;
  }, [onPlanChanged]);

  // Phase 6a: a decision or a start sent from the Otto panel: this page reads its view again.
  const panelStamp = usePanelStamp();
  useEffect(() => {
    let live = true;
    api
      .getMigration(importId)
      .then((next) => {
        if (live) setView(next);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [importId, panelStamp]);

  // The first answer (the GET may have made the plan) and the end of a measurement both tell the app.
  const lastBusy = useRef<boolean | null>(null);
  useEffect(() => {
    if (!view) return;
    const before = lastBusy.current;
    lastBusy.current = view.busy;
    if (before === null || (before && !view.busy)) planChanged.current();
  }, [view]);

  // While measuring, ask again every second. Not while a button's own call is on its way: its answer is newer.
  const polling =
    view !== null &&
    (view.busy || view.systems.some((s) => s.change?.busy === true)) &&
    !acting;
  useEffect(() => {
    if (!polling) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .getMigration(importId)
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
    return (
      <section aria-labelledby="migration-title" className="space-y-4">
        <h1
          id="migration-title"
          className="text-2xl font-semibold tracking-tight text-slate-50"
        >
          Migration
        </h1>
        {error ? (
          <ErrorBox title="The migration plan couldn't be loaded">
            {error}
          </ErrorBox>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </section>
    );
  }

  const current = view;
  // (On a page of its own, the 5c fixes, only the system the address names is shown: never the first one in its place.)
  const system =
    current.systems.find((s) => s.key === selectedKey) ??
    (dismissed || asPage || tab !== "systems" ? null : (current.systems[0] ?? null));

  async function act(call: () => Promise<MigrationView>, tellApp: boolean) {
    setActing(true);
    setError(null);
    try {
      setView(await call());
      if (tellApp) planChanged.current();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setActing(false);
    }
  }

  async function download() {
    setActing(true);
    setError(null);
    try {
      setExported(await downloadEvidence(current.plan_id));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setActing(false);
    }
  }

  // After a change-box call: this screen's own view again, then the app (the step bar and Fixes may have changed).
  async function reloadAfterChange() {
    setView(await api.getMigration(importId));
    planChanged.current();
  }

  function setting(
    systemKey: string,
    field: MigrationSettingField["field"],
    value: string,
  ) {
    void act(
      () => api.saveMigrationSetting(current.plan_id, systemKey, field, value),
      true,
    );
  }

  function saveChoice(
    systemKey: string,
  ): (option: MigrationOptionKey) => SaveChoice {
    return (option) => async (reason, reviewDate) => {
      setActing(true);
      setError(null);
      try {
        const next = await api.saveMigrationChoice(
          current.plan_id,
          systemKey,
          option,
          reason,
          reviewDate,
        );
        setView(next);
        setChoosing(null);
        planChanged.current();
        return null;
      } catch (e) {
        return {
          message: errorMessage(e),
          field: e instanceof ApiError ? e.field : null,
        };
      } finally {
        setActing(false);
      }
    };
  }

  const measure = current.measure;
  const tabClass = (active: boolean) =>
    `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
      active
        ? "bg-slate-800 text-slate-50 shadow-sm"
        : "text-slate-400 hover:text-slate-100"
    }`;

  // Summary cards: the systems, counted by the status the backend sent for each (never a score).
  const byStatus = new Map<string, { label: string; count: number }>();
  for (const s of current.systems) {
    const found = byStatus.get(s.status.code);
    if (found) found.count += 1;
    else byStatus.set(s.status.code, { label: s.status.label, count: 1 });
  }
  const cards = [
    {
      key: "systems",
      label: "Systems in the file",
      value: current.systems.length,
    },
    ...Array.from(byStatus.entries())
      .slice(0, 3)
      .map(([code, v]) => ({
        key: code,
        label: v.label,
        value: v.count,
        sub: "systems with this status",
      })),
  ];
  const needle = search.trim().toLowerCase();
  // The open system stays listed whatever the search, as before the panel.
  const listed = current.systems.filter(
    (s) =>
      s.key === system?.key ||
      (statusFilter === "all" || s.status.code === statusFilter) &&
      (!needle || [s.name, s.kind_label, s.plan_line, s.status.label].some((t) => t.toLowerCase().includes(needle))),
  );
  const statusOptions = [
    { value: "all", label: "All statuses" },
    ...Array.from(byStatus.entries()).map(([code, v]) => ({ value: code, label: v.label })),
  ];

  // Two columns, so the table still fits beside the open detail panel: each track's name above its status, then the
  // plan line, in the order of the cards before the table.
  // Phase 5b: beside an open panel, a row is the system, its track statuses and its plan line (which names its roadmap
  // phase), each in the backend's own words.
  const compactColumns: Column<MigrationSystem>[] = [
    {
      key: "system",
      header: "System",
      minWidth: 150,
      render: (s) => (
        <>
          <span className="block text-sm font-medium text-slate-100">{s.name}</span>
          {s.plan_line ? <span className="block text-xs text-slate-400">{s.plan_line}</span> : null}
          <OttoMark system={s} />
        </>
      ),
    },
    {
      key: "status",
      header: "Tracks",
      minWidth: 120,
      render: (s) =>
        (s.tracks_brief ?? []).length > 0 ? (
          <span className="flex flex-col items-start gap-1">
            {(s.tracks_brief ?? []).map((brief, i) => (
              <span key={i} data-testid="compact-track" className="flex flex-col items-start gap-0.5">
                <span className="text-[11px] text-slate-400">{brief.title}</span>
                <StatusPill status={brief.status} />
              </span>
            ))}
          </span>
        ) : (
          <StatusPill status={s.status} />
        ),
    },
  ];
  const columns: Column<MigrationSystem>[] = [
    {
      key: "system",
      header: "System",
      minWidth: 160,
      render: (s) => (
        <div className="min-w-0">
          <span className="block text-xs text-slate-400">{s.kind_label}</span>
          <span className="block text-sm font-medium text-slate-100">{s.name}</span>
          <OttoMark system={s} />
        </div>
      ),
    },
    {
      key: "status",
      header: "Status and plan",
      render: (s) => (
        <div className="flex flex-col items-start gap-2">
          {(s.tracks_brief ?? []).length > 0 ? (
            (s.tracks_brief ?? []).map((brief, i) => (
              <span key={i} data-testid="card-track" className="flex flex-col items-start gap-0.5">
                <span className="text-[11px] text-slate-400">{brief.title}</span>
                <StatusPill status={brief.status} />
              </span>
            ))
          ) : (
            <StatusPill status={s.status} />
          )}
          <span className="text-xs text-slate-400">{s.plan_line}</span>
        </div>
      ),
    },
  ];

  const panel = (
    <DetailPanel
      open={system !== null}
      item={system?.key ?? null}
      title={system?.kind_label ?? ""}
      onClose={closePanel}
    >
      {system ? (
        <SystemDetail
          key={system.key}
          system={system}
          busy={acting}
          detailsOpen={detailsOpen.has(system.key)}
          onDetailsOpen={(open) =>
            setDetailsOpen((prev) => {
              const next = new Set(prev);
              if (open) next.add(system.key);
              else next.delete(system.key);
              return next;
            })
          }
          openOption={choosing?.system === system.key ? choosing.option : null}
          onOpenOption={(option) => setChoosing(option ? { system: system.key, option } : null)}
          onSetting={(field, value) => setting(system.key, field, value)}
          onSaveChoice={saveChoice(system.key)}
          onViewFix={onViewFix}
          planId={current.plan_id}
          onChanged={reloadAfterChange}
        />
      ) : null}
      {system ? <RelatedFor itemKey={`system:${system.key}`} /> : null}
    </DetailPanel>
  );

  return (
    <section aria-label={current.title}>
      <PageHeader
        eyebrow={current.is_demo ? <DemoDataLabel /> : undefined}
        title={current.title}
        description={
          <span data-testid="migration-subline">
            <RichTextView parts={current.subline} />
          </span>
        }
        actions={
          <div className="flex max-w-xs flex-col items-end gap-1.5">
            <SecondaryButton
              disabled={acting || !measure.enabled}
              onClick={() =>
                void act(() => api.measureMigration(current.plan_id), false)
              }
            >
              {measure.label}
            </SecondaryButton>
            {measure.progress_text ? (
              <p
                role="status"
                data-testid="measure-progress"
                className="text-right text-xs text-slate-300"
              >
                {measure.progress_text}
              </p>
            ) : null}
            {!measure.enabled && measure.blocked_reason ? (
              <p
                data-testid="measure-blocked"
                className="text-right text-xs text-slate-400"
              >
                {measure.blocked_reason}
              </p>
            ) : null}
          </div>
        }
      />

      {error ? (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      <p
        data-testid="disclaimer"
        className="mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300"
      >
        {current.disclaimer}
      </p>

      <div
        role="group"
        aria-label="Migration views"
        className="mt-5 inline-flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1"
      >
        <button
          type="button"
          aria-pressed={tab === "systems"}
          onClick={() => setTab("systems")}
          className={tabClass(tab === "systems")}
        >
          {current.tabs.systems}
        </button>
        <button
          type="button"
          aria-pressed={tab === "roadmap"}
          onClick={() => setTab("roadmap")}
          className={tabClass(tab === "roadmap")}
        >
          {current.tabs.roadmap}
        </button>
        <button
          type="button"
          aria-pressed={tab === "dependencies"}
          onClick={() => setTab("dependencies")}
          className={tabClass(tab === "dependencies")}
        >
          {current.tabs.dependencies}
        </button>
      </div>

      <div className="mt-5">
        {tab === "dependencies" ? (
          // A list, a tie or a measurement can add or remove a named blocker: this screen's view again, then the app.
          <DependenciesView
            importId={importId}
            onViewFix={onViewFix}
            onChanged={() => void reloadAfterChange()}
            openItem={openItem}
          />
        ) : tab === "roadmap" ? (
          <TableWithPanel
            panelOpen={system !== null}
            table={
              <Roadmap
                view={current}
                busy={acting}
                exported={exported}
                onDownload={() => void download()}
                onViewFix={onViewFix}
                selectedKey={system?.key ?? null}
                onOpenSystem={openSystem}
              />
            }
            panel={panel}
          />
        ) : current.systems.length > 0 ? (
          <>
            <SummaryCards label="Systems by status" cards={cards} />
            <TableWithPanel
              panelOpen={system !== null}
              table={
                <nav aria-labelledby="migration-list-title" className="min-w-0">
                  <h2 id="migration-list-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
                    {current.list_title}
                  </h2>
                  <Toolbar>
                    <SearchInput value={search} onChange={setSearch} label="Search systems" placeholder="Search systems" />
                    <FilterSelect label="Status" value={statusFilter} options={statusOptions} onChange={setStatusFilter} />
                  </Toolbar>
                  <DataTable
                    label="Systems"
                    columns={columns}
                    rows={listed}
                    rowKey={(s) => s.key}
                    rowTestId="system-card"
                    compactColumns={compactColumns}
                    rowAttrs={(s) => ({ "data-system": s.key, "aria-current": s.key === system?.key ? "true" : undefined })}
                    selectedKey={system?.key ?? null}
                    onRowClick={(s) => openSystem(s.key)}
                    empty="No systems match this search."
                  />
                </nav>
              }
              panel={panel}
            />
          </>
        ) : current.empty_text ? (
          <p data-testid="migration-empty" className="text-sm text-slate-400">
            {current.empty_text}
          </p>
        ) : null}
      </div>
    </section>
  );
}
