import { useCallback, useContext, useEffect, useState } from "react";
import { usePanelStamp } from "../changes";
import { api, errorMessage, type FixSection, type FixesView } from "../api";
import { ChangeBox } from "./change/ChangeBox";
import { FixTable } from "./fixes/FixTable";
import { FixSections } from "./fixes/FixSections";
import { FixSummary, type FixRequest } from "./fixes/FixSummary";
import { DetailPanel, ItemPageContext, PageHeader, SummaryCards, TableWithPanel } from "./layout";
import { RelatedFor } from "./related";
import { DemoDataLabel, ErrorBox } from "./ui";

const POLL_MS = 1000;

interface Props {
  planId: number;
  /** The fix to show. Without one, or when it is not in the list, the first fix is shown. */
  selectedId: string | null;
  onSelect: (fixId: string) => void;
  /** "Retest now" has started the retest: the app opens Evidence Lab on the result it retests (its before and after). */
  onRetestStarted: (item?: string | null) => void;
  /** A change was tried, approved, applied or rolled back: the app loads the plan again. */
  onPlanChanged?: () => void;
  /** Phase 5b: a work group to start filtered to. */
  group?: string | null;
}

/** The Fixes step. Every word, status and button comes from the backend; this screen works nothing out. */
export function FixesScreen({ planId, selectedId, onSelect, onRetestStarted, onPlanChanged, group = null }: Props) {
  const [view, setView] = useState<FixesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The sections the user opened or closed, by fix and section. The others keep the state the backend sent.
  const [toggled, setToggled] = useState<Readonly<Record<string, boolean>>>({});
  const [pollTick, setPollTick] = useState(0);
  // The fix whose panel is open. A fix chosen from outside (View in Fixes) opens its panel too.
  const [openId, setOpenId] = useState<string | null>(selectedId);
  // As before the panel, the page opens on the first fix until the person closes the panel (then it stays closed).
  const [dismissed, setDismissed] = useState(false);
  const asPage = Boolean(useContext(ItemPageContext)?.asPage);
  const [seenSelected, setSeenSelected] = useState<string | null>(selectedId);
  if (selectedId !== seenSelected) {
    setSeenSelected(selectedId);
    setOpenId(selectedId);
    setDismissed(false);
  }
  // Escape also closes the merge confirm box; while that box is open it is the only thing that closes.
  const closePanel = useCallback(() => {
    if (document.querySelector('[role="dialog"]')) return;
    setOpenId(null);
    setDismissed(true);
  }, []);

  // Phase 6a: a decision or a start sent from the Otto panel: this page reads its view again.
  const panelStamp = usePanelStamp();
  useEffect(() => {
    let live = true;
    api
      .getFixes(planId)
      .then((next) => {
        if (live) setView(next);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId, panelStamp]);

  // While a proof (or anything else) runs, ask again every second. Not while a button's own call is
  // on its way: its answer is the newer view, and an older one must not land on top of it.
  const polling = view !== null && (view.busy || view.fixes.some((f) => f.change_box?.busy === true)) && !busy;
  useEffect(() => {
    if (!polling) return;
    let live = true;
    const timer = setTimeout(() => {
      api
        .getFixes(planId)
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
  }, [planId, polling, pollTick]);

  if (!view) {
    return (
      <section aria-labelledby="fixes-title" className="space-y-4">
        <h1 id="fixes-title" className="text-2xl font-semibold tracking-tight text-slate-50">
          Fixes
        </h1>
        {error ? (
          <ErrorBox title="The fixes couldn't be loaded">{error}</ErrorBox>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </section>
    );
  }

  const current = view;
  // (On a page of its own, the 5c fixes, only the fix the address names is shown: never the first one in its place.)
  const fix = current.fixes.find((f) => f.id === openId) ?? (dismissed || asPage ? null : (current.fixes[0] ?? null));
  const choose = (fixId: string) => {
    setOpenId(fixId);
    setDismissed(false);
    onSelect(fixId);
  };
  // One card for each status word the backend sent, counted by that word (no wording of our own). Phase 5b: counted by
  // the word, not the key, because the statuses of a change box share one key while each has its own word.
  const byStatus = new Map<string, { word: string; n: number }>();
  for (const f of current.fixes) {
    const seen = byStatus.get(f.status.word);
    if (seen) seen.n += 1;
    else byStatus.set(f.status.word, { word: f.status.word, n: 1 });
  }

  async function act(call: () => Promise<FixesView>) {
    setBusy(true);
    setError(null);
    try {
      setView(await call());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  // After a change-box call: this screen's own view again, then the app.
  async function reloadAfterChange() {
    setView(await api.getFixes(planId));
    onPlanChanged?.();
  }

  // Phase 5c: after a decision on one of Otto's proposals (accept, reject, undo, reconsider): this screen's own view
  // again, so the fix's buttons and words are the backend's for the new state. The decision itself ran nothing.
  async function reloadAfterDecision() {
    // A read that was already on its way while a proof runs was asked before the decision: its answer is dropped, so
    // it can't land on top of the newer view.
    setPollTick((n) => n + 1);
    try {
      setView(await api.getFixes(planId));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  // The same retest as "Retest new version". Its progress and the before and after show in Evidence Lab.
  async function retest(fixId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.retestNow(current.plan_id, fixId);
      const fix = current.fixes.find((f) => f.id === fixId);
      onRetestStarted(fix?.came_from_links?.[0]?.link.item ?? null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function request(fixId: string, asked: FixRequest) {
    const plan = current.plan_id;
    switch (asked.action) {
      case "connect":
        return void act(() => api.connectCode(plan));
      case "run_proof_again":
        return void act(() => api.runProofAgain(plan, fixId));
      case "open_pull_request":
        return void act(() => api.openPullRequest(plan, fixId, asked.reviewers));
      case "approve":
        return void act(() => api.approve(plan, fixId, asked.reviewer));
      case "merge":
        return void act(() => api.mergePullRequest(plan, fixId));
      case "retest_now":
        return void retest(fixId);
    }
  }

  const sectionKey = (fixId: string, section: FixSection) => `${fixId}/${section.key}`;

  return (
    <section aria-label={current.title}>
      <PageHeader
        eyebrow={current.is_demo ? <DemoDataLabel /> : undefined}
        title={current.title}
        description={<span data-testid="fixes-subline">{current.subline}</span>}
      />

      {error ? (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      <p data-testid="disclaimer" className="mb-2 mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        {current.disclaimer}
      </p>

      {/* With the four groups, each empty group says why itself; the page's own sentence is for a view without them. */}
      {current.fixes.length === 0 && current.empty_text && (current.groups ?? []).length === 0 ? (
        <p data-testid="fixes-empty" className="mt-6 text-sm text-slate-400">
          {current.empty_text}
        </p>
      ) : null}
      {current.fixes.length > 0 || (current.groups ?? []).length > 0 ? (
        <div className="mt-6">
          {current.fixes.length > 0 ? (
          <SummaryCards
            label="Fixes summary"
            cards={[
              { key: "fixes", label: "Fixes", value: current.fixes.length },
              ...Array.from(byStatus, ([key, { word, n }]) => ({ key, label: word, value: n })).slice(0, 3),
            ]}
          />
          ) : null}
          <TableWithPanel
            panelOpen={fix !== null}
            table={
              <FixTable
                title={current.list_title}
                fixes={current.fixes}
                groups={current.groups ?? []}
                selectedId={fix?.id ?? null}
                onSelect={choose}
                group={group}
              />
            }
            panel={
              <DetailPanel
                open={fix !== null}
                item={fix?.id ?? null}
                title={fix?.title ?? ""}
                onClose={closePanel}
              >
                {fix ? (
                  <div className="flex min-w-0 flex-col gap-3">
                    {/* The key gives each fix its own ticks and its own confirm box. */}
                    <FixSummary
                      key={fix.id}
                      fix={fix}
                      busy={busy}
                      onRequest={(asked) => request(fix.id, asked)}
                      planId={current.plan_id}
                      onProposalDecided={() => void reloadAfterDecision()}
                    />
                    {fix.sections_note ? (
                      <p data-testid="fix-sections-note" className="px-1 text-xs text-slate-400">
                        {fix.sections_note}
                      </p>
                    ) : null}
                    {fix.change_box ? (
                      <ChangeBox
                        key={fix.change_box.id}
                        change={fix.change_box}
                        planId={current.plan_id}
                        onChanged={reloadAfterChange}
                        onViewFix={choose}
                      />
                    ) : null}
                    <FixSections
                      sections={fix.sections}
                      advisories={fix.advisories}
                      isOpen={(section) => toggled[sectionKey(fix.id, section)] ?? section.open}
                      onToggle={(section) =>
                        setToggled((prev) => {
                          const key = sectionKey(fix.id, section);
                          return { ...prev, [key]: !(prev[key] ?? section.open) };
                        })
                      }
                    />
                    <RelatedFor itemKey={`fix:${fix.id}`} />
                  </div>
                ) : null}
              </DetailPanel>
            }
          />
        </div>
      ) : null}
    </section>
  );
}
