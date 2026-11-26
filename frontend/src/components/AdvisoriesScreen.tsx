import { useEffect, useRef, useState } from "react";
import { usePanelStamp } from "../changes";
import { NewAdvisories } from "./advisories/NewAdvisories";
import { api, errorMessage, type AdvisoriesView, type OttoProposal } from "../api";
import { AdvisoryPanel } from "./advisories/AdvisoryPanel";
import { AdvisoryTable } from "./advisories/AdvisoryTable";
import { FoldLine } from "./foldline";
import { FilterSelect, PageHeader, SearchInput, SummaryCards, TableWithPanel, Toolbar } from "./layout";
import { ItemLinkView } from "./related";
import { HistoryOfPage } from "./evidence/HistoryFold";
import { ErrorBox } from "./ui";

interface Props {
  planId: number;
  /** An advisory to open (from a link: #/a/<id>/advisories?item=<advisory id>). */
  openItem?: string | null;
  /** A decision was recorded (an accepted check joins the test plan, an undone one leaves it): the app reads its copy
   * of the plan again. */
  onPlanChanged?: () => void;
  /** Phase 6b: the Decision filter the address names, and how a change of it goes back into the address. */
  decision?: string | null;
  onFilters?: (filters: { decision?: string | null }) => void;
}

/** The view with one proposal replaced by what the backend answered for it. */
function withProposal(view: AdvisoriesView, next: OttoProposal): AdvisoriesView {
  return {
    ...view,
    rows: view.rows.map((row) => ({
      ...row,
      panel: {
        ...row.panel,
        here: {
          ...row.panel.here,
          rows: row.panel.here.rows.map((here) => (here.proposal?.id === next.id ? { ...here, proposal: next } : here)),
        },
      },
    })),
  };
}

/** Phase 5c: Advisories. Every published advisory in the installed test packs: whether it has a test, which signing
 * programs of this assessment it fits, where Otto's proposed check stands, and the latest result of that check here.
 * Otto proposes; a person decides: each proposed check is accepted or rejected by itself, in the advisory's panel.
 * There is no button that decides several at once, and a decision runs nothing. Every word, label and tone is the
 * backend's: this page words no result and decides none. */
export function AdvisoriesScreen({ planId, openItem = null, onPlanChanged, decision = null, onFilters }: Props) {
  const [view, setView] = useState<AdvisoriesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [testFilter, setTestFilter] = useState("all");
  const [decisionFilter, setDecisionFilterState] = useState(decision ?? "all");
  const setDecisionFilter = (value: string) => {
    setDecisionFilterState(value);
    onFilters?.({ decision: value === "all" ? null : value });
  };
  useEffect(() => setDecisionFilterState(decision ?? "all"), [decision]);
  const [resultFilter, setResultFilter] = useState("all");
  const [openId, setOpenId] = useState<string | null>(openItem);
  // The newest request for the page's view: an answer that comes back after a newer one was asked for is dropped.
  const asked = useRef(0);
  // Phase 6a: a decision or a start sent from the Otto panel: this page reads its view again.
  const panelStamp = usePanelStamp();

  useEffect(() => setOpenId(openItem), [openItem]);

  useEffect(() => {
    const mine = ++asked.current;
    api
      .getAdvisories(planId)
      .then((next) => {
        if (asked.current !== mine) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (asked.current === mine) setError(errorMessage(e));
      });
    return () => {
      asked.current += 1;
    };
  }, [planId, panelStamp]);

  // Phase 6: while a research run goes on, ask again every few seconds (its progress, and at its end the new pack's
  // advisories and proposals).
  const researching = view?.lookup?.busy === true;
  useEffect(() => {
    if (!researching) return;
    const mine = asked.current;
    const timer = setTimeout(() => {
      api
        .getAdvisories(planId)
        .then((next) => {
          if (asked.current === mine) setView(next);
        })
        .catch(() => undefined);
    }, 3000);
    return () => clearTimeout(timer);
  }, [researching, view, planId]);

  /** A decision was recorded. The card's own answer is shown at once; then the whole page is read again, because a
   * decision also moves the row's cells, the waiting line and the check's place in the test plan; and the app is told,
   * so that it reads its copy of the test plan again. */
  function decided(next: OttoProposal) {
    setView((v) => (v ? withProposal(v, next) : v));
    setReloadError(null);
    const mine = ++asked.current;
    api
      .getAdvisories(planId)
      .then((fresh) => {
        if (asked.current === mine) setView(fresh);
      })
      .catch((e: unknown) => {
        if (asked.current === mine) setReloadError(errorMessage(e));
      });
    onPlanChanged?.();
  }

  if (!view) {
    return (
      <section data-testid="advisories-page" aria-label="Advisories">
        <PageHeader title="Advisories" />
        {error ? (
          <ErrorBox>{error}</ErrorBox>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </section>
    );
  }

  const needle = search.trim().toLowerCase();
  const rows = view.rows.filter(
    (r) =>
      (testFilter === "all" || r.test.key === testFilter) &&
      // A row whose check fits several programs can stand in more than one state: it matches each of them.
      (decisionFilter === "all" ||
        r.proposal.key === decisionFilter ||
        (r.proposal.keys ?? []).includes(decisionFilter)) &&
      (resultFilter === "all" || r.result.key === resultFilter) &&
      (!needle || r.search.toLowerCase().includes(needle)),
  );
  const opened = view.rows.find((r) => r.id === openId) ?? null;
  const waiting = view.waiting;

  return (
    <section data-testid="advisories-page" aria-label={view.title}>
      <PageHeader
        title={view.title}
        description={view.subline}
        actions={<HistoryOfPage area="advisories" page="Advisories" />}
      />

      {/* Otto is not on this computer: a calm notice in the backend's words, not an error. */}
      {!view.otto.installed ? (
        <p
          role="note"
          data-testid="advisories-otto-line"
          data-installed="false"
          className="mb-4 break-words rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-slate-200"
        >
          {view.otto.line}
        </p>
      ) : null}

      {/* The design refactor (26 November 2026): four numbers first, counted from the rows below, so the list starts on
          the first screen. */}
      {view.rows.length > 0 ? (
        <SummaryCards
          label="Advisories summary"
          cards={[
            { key: "advisories", label: view.title, value: view.rows.length, sub: "in the installed test packs" },
            {
              key: "ready",
              label: view.filters.test.find((o) => o.key === "ready")?.label ?? "Test ready",
              value: view.rows.filter((r) => r.test.key === "ready").length,
            },
            { key: "waiting", label: "Waiting for your decision", value: waiting.count, sub: "proposed checks" },
            {
              key: "results",
              label: view.columns[view.columns.length - 1] ?? "Result here",
              value: view.rows.filter((r) => ["fail", "pass", "warn"].includes(r.result.key)).length,
              sub: "advisories with a result here",
            },
          ]}
        />
      ) : null}

      {/* Waiting for you: how many proposed checks nobody has decided yet. It has no button, on purpose: each proposal
          is decided by itself, in its advisory's panel. */}
      <div
        data-testid="advisories-waiting"
        data-count={waiting.count}
        className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3"
      >
        <p
          data-testid="advisories-waiting-line"
          className={`break-words text-sm ${waiting.count > 0 ? "font-medium text-slate-100" : "text-slate-200"}`}
        >
          {waiting.line}
        </p>
        {waiting.blocked_reason && waiting.blocked_reason !== waiting.line ? (
          <p data-testid="advisories-waiting-reason" className="mt-1 break-words text-sm text-slate-300">
            {waiting.blocked_reason}
          </p>
        ) : null}
        <p data-testid="advisories-waiting-note" className="mt-2 break-words text-xs text-slate-400">
          {waiting.note}
        </p>
        {reloadError ? (
          <div className="mt-3">
            <ErrorBox>{reloadError}</ErrorBox>
          </div>
        ) : null}
      </div>

      {/* Where the page's facts come from: the installed packs, the answers and the harness, in one folded line. */}
      <div className="mb-5">
        <FoldLine title="Where this page's facts come from" hint={view.packs_line} testId="advisories-facts">
          <ul className="space-y-1 text-xs text-slate-400">
            {/* The whole line is the link (to Settings, Test packs): the view sends the line and where it goes, no other words. */}
            <li data-testid="advisories-packs-line" className="w-fit max-w-full">
              <ItemLinkView
                link={view.packs_link}
                className="block break-words text-sky-300 underline-offset-2 hover:underline"
              >
                {view.packs_line}
              </ItemLinkView>
            </li>
            <li data-testid="advisories-answers-line">{view.answers_line}</li>
            {view.otto.installed ? (
              <li data-testid="advisories-otto-line" data-installed="true">
                {view.otto.line}
              </li>
            ) : null}
          </ul>
        </FoldLine>
      </div>

      {/* Phase 6, Otto's research loop: look for newly published advisories, and prove a test for each on public copies. */}
      {view.lookup ? (
        <NewAdvisories
          planId={planId}
          lookup={view.lookup}
          onView={(next) => {
            asked.current += 1; // (an older read of the page must not land on top of this answer)
            setView(next);
            onPlanChanged?.();
          }}
        />
      ) : null}

      <Toolbar>
        <SearchInput
          value={search}
          onChange={setSearch}
          label="Search advisories"
          placeholder="Search advisories"
          testId="advisories-search"
        />
        <FilterSelect
          label="Test"
          value={testFilter}
          options={view.filters.test.map((o) => ({ value: o.key, label: o.label }))}
          onChange={setTestFilter}
          testId="advisories-filter-test"
        />
        <FilterSelect
          label="Decision"
          value={decisionFilter}
          options={view.filters.decision.map((o) => ({ value: o.key, label: o.label }))}
          onChange={setDecisionFilter}
          testId="advisories-filter-decision"
        />
        <FilterSelect
          label="Result"
          value={resultFilter}
          options={view.filters.result.map((o) => ({ value: o.key, label: o.label }))}
          onChange={setResultFilter}
          testId="advisories-filter-result"
        />
      </Toolbar>

      <TableWithPanel
        panelOpen={opened !== null}
        table={
          <AdvisoryTable
            label={view.title}
            names={view.columns}
            rows={rows}
            selectedId={openId}
            onOpen={(r) => setOpenId(r.id === openId ? null : r.id)}
            empty={
              view.rows.length === 0 ? (
                view.empty ? (
                  <span data-testid="advisories-empty">{view.empty}</span>
                ) : undefined
              ) : (
                <span data-testid="advisories-no-match">Nothing matches these filters.</span>
              )
            }
          />
        }
        panel={<AdvisoryPanel planId={planId} row={opened} onClose={() => setOpenId(null)} onDecided={decided} />}
      />

      {/* The standing line, once on the screen (SPEC section 11), as a quiet line at the foot. */}
      <p
        data-testid="advisories-standing"
        className="mt-5 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300"
      >
        {view.standing_line}
      </p>
    </section>
  );
}
