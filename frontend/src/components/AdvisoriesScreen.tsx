import { useEffect, useState } from "react";
import { api, errorMessage, type AdvisoriesView } from "../api";
import { AdvisoryPanel } from "./advisories/AdvisoryPanel";
import { AdvisoryTable } from "./advisories/AdvisoryTable";
import { FilterSelect, PageHeader, SearchInput, TableWithPanel, Toolbar } from "./layout";
import { ItemLinkView } from "./related";
import { ErrorBox, PrimaryButton, Spinner } from "./ui";

interface Props {
  planId: number;
  /** An advisory to open (from a link: #/a/<id>/advisories?item=<advisory id>). */
  openItem?: string | null;
  /** Add new checks put tests in the test plan: the app reads its copy of the plan again. */
  onPlanChanged?: () => void;
}

/** Phase 5c: Advisories. Every published advisory in the installed test packs: whether it has a test, which signing
 * programs of this assessment it fits, and the latest result of its check here. One button, Add new checks, adds the
 * packs' tests to the test plan; it runs nothing. Every word, label and tone is the backend's: this page words no
 * result and decides none. */
export function AdvisoriesScreen({ planId, openItem = null, onPlanChanged }: Props) {
  const [view, setView] = useState<AdvisoriesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [testFilter, setTestFilter] = useState("all");
  const [resultFilter, setResultFilter] = useState("all");
  const [openId, setOpenId] = useState<string | null>(openItem);

  useEffect(() => setOpenId(openItem), [openItem]);

  useEffect(() => {
    let live = true;
    api
      .getAdvisories(planId)
      .then((next) => {
        if (!live) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId]);

  async function addNewChecks() {
    setAdding(true);
    setAddError(null);
    try {
      // The answer is the whole page as it now stands.
      setView(await api.addNewChecks(planId));
      onPlanChanged?.();
    } catch (e) {
      setAddError(errorMessage(e));
    } finally {
      setAdding(false);
    }
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
      (resultFilter === "all" || r.result.key === resultFilter) &&
      (!needle || r.search.toLowerCase().includes(needle)),
  );
  const opened = view.rows.find((r) => r.id === openId) ?? null;
  const add = view.add;

  return (
    <section data-testid="advisories-page" aria-label={view.title}>
      <PageHeader title={view.title} description={view.subline} />

      <p data-testid="advisories-standing" className="mb-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        {view.standing_line}
      </p>

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

      <ul className="mb-5 space-y-1 text-xs text-slate-400">
        {/* The whole line is the link (to Settings, Test packs): the view sends the line and where it goes, no other words. */}
        <li data-testid="advisories-packs-line" className="w-fit max-w-full">
          <ItemLinkView link={view.packs_link} className="block break-words text-sky-300 underline-offset-2 hover:underline">
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

      <div data-testid="advisories-add" className="mb-5 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <PrimaryButton testId="add-new-checks" disabled={!add.can} busy={adding} onClick={() => void addNewChecks()}>
            {adding ? <Spinner className="h-3.5 w-3.5" /> : null}
            {add.button}
          </PrimaryButton>
          {add.blocked_reason ? (
            <p data-testid="add-new-checks-reason" className="min-w-0 flex-1 basis-64 break-words text-sm text-slate-300">
              {add.blocked_reason}
            </p>
          ) : null}
        </div>
        <p data-testid="add-new-checks-note" className="mt-2 text-xs text-slate-400">
          {add.note}
        </p>
        {addError ? (
          <div className="mt-3">
            <ErrorBox>{addError}</ErrorBox>
          </div>
        ) : null}
      </div>

      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search advisories" placeholder="Search advisories" testId="advisories-search" />
        <FilterSelect
          label="Test"
          value={testFilter}
          options={view.filters.test.map((o) => ({ value: o.key, label: o.label }))}
          onChange={setTestFilter}
          testId="advisories-filter-test"
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
        panel={<AdvisoryPanel planId={planId} row={opened} onClose={() => setOpenId(null)} />}
      />
    </section>
  );
}
