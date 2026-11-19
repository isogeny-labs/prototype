import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorMessage, type AssistantDecision, type AssistantEntry, type AssistantStep, type AssistantTab, type AssistantThread, type AssistantView } from "../../api";
import { fromPanel, useChangeStamp } from "../../changes";
import { prefs, type OttoTabs } from "../../prefs";
import type { Page } from "../../router";
import { FromOttoTag, ProposalStatusChip } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { ErrorBox, PrimaryButton, SecondaryButton, Spinner, StatusChip } from "../ui";
import { pageAfter, sendStep } from "./send";

const POLL_MS = 2000;
/** How many entries of a thread so far show before "Show all". */
const SO_FAR_SHOWN = 6;

/** Who a decision is recorded as, as the backend words it, and whether the name is asked for now. */
type Who = AssistantView["recorded_as"] & { ask: boolean };

/** Which button of which entry is at its Confirm step. Only one at a time. */
interface Confirming {
  entry: string;
  /** A decision's key ("accept", "reject", "undo", "reconsider"), or "step" for a next step. */
  key: string;
}

/** Phase 6a: the Otto assistant, the right-hand panel beside every page of an assessment.
 *
 * It makes one read (this assessment, this page, this open item) and draws what the backend sent: the status line, up
 * to three tabs (Testing, Fixing, Planning), what fits this page, what waits elsewhere and the selected thread so far.
 * Every word, every button state and every reason is the backend's. The panel decides nothing and has no request of
 * its own: a button first shows what it will do and waits for Confirm, and Confirm sends the very request the page's
 * own button sends (a decision through `api.decideProposal`, a next step through `sendStep`). Looking at the panel,
 * or switching and closing its tabs, sends nothing but that one read. */
export function OttoPanel({
  assessmentId,
  page,
  item,
  onGo,
}: {
  assessmentId: number;
  page: Page;
  /** The item open on the page (its side panel), if any. */
  item: string | null;
  /** Opens a page of this assessment, as the page itself does after its button's answer. */
  onGo: (page: Page) => void;
}) {
  const [view, setView] = useState<AssistantView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const changed = useChangeStamp();
  const asked = useRef(0);

  useEffect(() => {
    const mine = ++asked.current;
    api
      .getAssistant(assessmentId, page, item)
      .then((next) => {
        if (asked.current !== mine) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (asked.current === mine) setError(errorMessage(e));
      });
  }, [assessmentId, page, item, changed, tick]);

  // While something runs, ask again (the page does the same for its own view).
  const busy = view?.busy === true && view.assessment_id === assessmentId;
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [busy, view]);

  // ---- the tabs: which are closed, which one is selected, and what was last seen in each (kept in this browser)
  const [tabPrefs, setTabPrefs] = useState<OttoTabs>(() => prefs.ottoTabs(assessmentId));
  useEffect(() => setTabPrefs(prefs.ottoTabs(assessmentId)), [assessmentId]);
  const saveTabs = useCallback(
    (change: (now: OttoTabs) => OttoTabs) => {
      setTabPrefs((now) => {
        const next = change(now);
        prefs.setOttoTabs(assessmentId, next);
        return next;
      });
    },
    [assessmentId],
  );
  const current = view && view.assessment_id === assessmentId ? view : null;
  const tabs = useMemo(() => (current?.tabs ?? []).filter((t) => tabPrefs.closed[t.key] !== t.mark), [current, tabPrefs]);
  // A tab picked by hand stays until the page changes; opening a page selects its own tab when that tab is open.
  const [picked, setPicked] = useState<AssistantThread | null>(null);
  const lastSelected = useRef<AssistantThread | null>(null);
  useEffect(() => setPicked(null), [page, assessmentId]);
  const pageThread = current?.thread ?? null;
  const selected: AssistantTab | null =
    tabs.find((t) => t.key === picked) ?? tabs.find((t) => t.key === pageThread) ?? tabs.find((t) => t.key === lastSelected.current) ?? tabs[0] ?? null;
  const selectedKey = selected?.key ?? null;
  const selectedMark = selected?.mark ?? null;
  useEffect(() => {
    if (selectedKey === null || selectedMark === null) return;
    lastSelected.current = selectedKey;
    // The open tab has been seen up to here: no dot for it, and it is no longer a closed tab that came back.
    saveTabs((now) => {
      if (now.seen[selectedKey] === selectedMark && !(selectedKey in now.closed)) return now;
      const closed = { ...now.closed };
      delete closed[selectedKey];
      return { closed, seen: { ...now.seen, [selectedKey]: selectedMark } };
    });
  }, [selectedKey, selectedMark, saveTabs]);

  function closeTab(tab: AssistantTab) {
    saveTabs((now) => ({ closed: { ...now.closed, [tab.key]: tab.mark }, seen: { ...now.seen, [tab.key]: tab.mark } }));
    if (picked === tab.key) setPicked(null);
    if (lastSelected.current === tab.key) lastSelected.current = null;
  }

  function reopen(thread: AssistantThread) {
    saveTabs((now) => {
      if (!(thread in now.closed)) return now;
      const closed = { ...now.closed };
      delete closed[thread];
      return { ...now, closed };
    });
  }

  // ---- the Confirm step: one button at a time
  const [confirming, setConfirming] = useState<Confirming | null>(null);
  const [reason, setReason] = useState("");
  // Who a decision is recorded as. A name is asked for once, at the first Confirm of a decision (and kept in Settings).
  const [name, setName] = useState("");
  const [nameAsked, setNameAsked] = useState(prefs.ottoNameAsked);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  useEffect(() => {
    setConfirming(null);
    setSendError(null);
  }, [page, assessmentId]);

  function ask(entry: AssistantEntry, key: string) {
    setConfirming({ entry: entry.id, key });
    setReason("");
    setSendError(null);
  }

  function cancel() {
    setConfirming(null);
    setReason("");
    setSendError(null);
  }

  async function confirm(send: () => Promise<unknown>, then?: Page | null) {
    setSending(true);
    setSendError(null);
    try {
      await fromPanel(send);
      setConfirming(null);
      setReason("");
      if (then) onGo(then);
    } catch (e) {
      setSendError(errorMessage(e));
    } finally {
      setSending(false);
    }
  }

  const planId = current?.plan_id ?? null;
  const card = (entry: AssistantEntry, compact = false) => (
    <EntryCard
      key={entry.id}
      entry={entry}
      compact={compact}
      confirming={confirming?.entry === entry.id ? confirming.key : null}
      reason={reason}
      onReason={setReason}
      sending={sending}
      error={confirming?.entry === entry.id ? sendError : null}
      onAsk={(key) => ask(entry, key)}
      onCancel={cancel}
      who={current ? { ...current.recorded_as, ask: !current.recorded_as.typed && !nameAsked } : null}
      name={name}
      onName={setName}
      onConfirmDecision={(decision) => {
        if (planId === null) return;
        const why = decision.key === "reject" ? reason.trim() || undefined : undefined;
        const typed = current && !current.recorded_as.typed && !nameAsked ? name.trim() : "";
        void confirm(async () => {
          // (the name, when one was typed, is kept first: the decision is then recorded under it)
          if (typed) await api.setDecisionName(typed);
          prefs.setOttoNameAsked();
          setNameAsked(true);
          setName("");
          return api.decideProposal(planId, entry.id, decision.key, why);
        });
      }}
      onConfirmStep={(step) => void confirm(() => sendStep(step.action), pageAfter(step.action) as Page | null)}
    />
  );

  return (
    <aside
      data-testid="otto-panel"
      aria-labelledby="otto-title"
      className="shrink-0 border-t border-slate-800 bg-slate-900/60 xl:sticky xl:top-14 xl:h-[calc(100vh-3.5rem)] xl:w-80 xl:overflow-y-auto xl:border-l xl:border-t-0"
    >
      <div className="px-4 pb-2 pt-4">
        <h2 id="otto-title" className="text-sm font-semibold text-slate-100">
          {current?.title ?? "Otto"}
        </h2>
        {current ? (
          <p data-testid="otto-status" data-live={current.status.live} className="mt-1 text-xs text-slate-400">
            {current.status.text}
            {current.status.link ? (
              <>
                {" "}
                <ItemLinkView link={current.status.link.link} testId="otto-status-link">
                  {current.status.link.label}
                </ItemLinkView>
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      {error ? (
        <div className="px-4 pb-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      {!current && !error ? (
        <p role="status" className="px-4 pb-4 text-sm text-slate-400">
          Loading…
        </p>
      ) : null}

      {current ? (
        <div className="space-y-4 px-4 pb-6 text-sm">
          {current.notices.map((notice) => (
            <p key={notice} data-testid="otto-notice" role="status" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-300">
              {notice}
            </p>
          ))}

          {tabs.length > 0 ? (
            <div role="tablist" aria-label="Threads" data-testid="otto-tabs" className="flex flex-wrap gap-1.5">
              {tabs.map((tab) => {
                const isSelected = tab.key === selectedKey;
                const dot = !isSelected && tabPrefs.seen[tab.key] !== tab.mark;
                return (
                  <span
                    key={tab.key}
                    data-testid="otto-tab"
                    data-thread={tab.key}
                    data-selected={isSelected}
                    data-dot={dot}
                    className={`inline-flex items-center rounded-lg border text-xs ${
                      isSelected ? "border-slate-500 bg-slate-800 text-slate-100" : "border-slate-700 bg-slate-900 text-slate-300"
                    }`}
                  >
                    <button
                      type="button"
                      role="tab"
                      id={`otto-tab-${tab.key}`}
                      aria-selected={isSelected}
                      aria-controls="otto-thread"
                      onClick={() => setPicked(tab.key)}
                      className="inline-flex items-center gap-1.5 rounded-l-lg py-1 pl-2.5 pr-1.5 font-medium hover:text-slate-50"
                    >
                      {dot ? (
                        <span data-testid="otto-tab-dot" className="h-1.5 w-1.5 rounded-full bg-sky-400">
                          <span className="sr-only">New: </span>
                        </span>
                      ) : null}
                      {tab.label}{" "}
                      <span
                        data-testid="otto-tab-count"
                        title={`${tab.waiting} waiting for a decision`}
                        className="rounded-full border border-slate-600 px-1.5 text-[11px] leading-4 text-slate-300"
                      >
                        {tab.waiting}
                        <span className="sr-only"> waiting for a decision</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      data-testid="otto-tab-close"
                      aria-label={`Close the ${tab.label} tab`}
                      title="Close this tab. It comes back when its thread has something new."
                      onClick={() => closeTab(tab)}
                      className="rounded-r-lg px-1.5 py-1 text-slate-400 hover:bg-slate-700 hover:text-slate-100"
                    >
                      <span aria-hidden="true">×</span>
                    </button>
                  </span>
                );
              })}
            </div>
          ) : null}

          <section data-testid="otto-on-page" aria-label={current.on_page.title}>
            <Heading>{current.on_page.title}</Heading>
            {current.on_page.entries.length > 0 ? (
              <div className="space-y-2.5">{current.on_page.entries.map((entry) => card(entry))}</div>
            ) : (
              <p data-testid="otto-empty" className="text-sm text-slate-400">
                {current.on_page.empty}
                {current.on_page.empty_link ? (
                  <>
                    {" "}
                    <ItemLinkView link={current.on_page.empty_link.link} testId="otto-empty-link">
                      {current.on_page.empty_link.label}
                    </ItemLinkView>
                  </>
                ) : null}
              </p>
            )}
          </section>

          {current.elsewhere.lines.length > 0 || current.elsewhere.empty ? (
            <section data-testid="otto-elsewhere" data-count={current.elsewhere.count} aria-label={current.elsewhere.title}>
              {current.elsewhere.lines.length > 0 ? (
                <>
                  <Heading>{current.elsewhere.title}</Heading>
                  <ul className="space-y-1.5">
                    {current.elsewhere.lines.map((line) => (
                      <li key={line.text} data-testid="otto-elsewhere-line" data-thread={line.thread} onClickCapture={() => reopen(line.thread)}>
                        <ItemLinkView link={line.link} className="break-words text-[13px] text-sky-300 underline-offset-2 hover:underline">
                          {line.text}
                        </ItemLinkView>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p data-testid="otto-nothing-waiting" className="text-[13px] text-slate-400">
                  {current.elsewhere.empty}
                </p>
              )}
            </section>
          ) : null}

          {selected ? (
            <SoFar key={selected.key} tab={selected} card={(entry) => card(entry, true)} />
          ) : null}

          <p data-testid="otto-note" className="border-t border-slate-800 pt-3 text-xs text-slate-500">
            {current.note}
          </p>
        </div>
      ) : null}
    </aside>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{children}</h3>;
}

/** The selected thread so far: decided suggestions with who and when, reviewed results, and where each fix stands, in
 * the order things happened. The newest few show; the rest unfold. */
function SoFar({ tab, card }: { tab: AssistantTab; card: (entry: AssistantEntry) => ReactNode }) {
  const [all, setAll] = useState(false);
  const entries = tab.so_far;
  const hidden = all ? 0 : Math.max(0, entries.length - SO_FAR_SHOWN);
  const shown = hidden > 0 ? entries.slice(hidden) : entries;
  return (
    <section id="otto-thread" role="tabpanel" aria-labelledby={`otto-tab-${tab.key}`} data-testid="otto-so-far" data-thread={tab.key}>
      <Heading>
        {tab.so_far_title}: {tab.label}
      </Heading>
      {entries.length === 0 ? (
        <p className="text-[13px] text-slate-400">{tab.so_far_empty}</p>
      ) : (
        <>
          {hidden > 0 ? (
            <button
              type="button"
              data-testid="otto-so-far-all"
              onClick={() => setAll(true)}
              className="mb-2 text-xs text-sky-300 underline-offset-2 hover:underline"
            >
              Show all {entries.length} (the {hidden} before these)
            </button>
          ) : null}
          <div className="space-y-2">{shown.map((entry) => card(entry))}</div>
        </>
      )}
    </section>
  );
}

function Mark({ entry }: { entry: AssistantEntry }) {
  if (entry.kind === "suggestion") return <FromOttoTag label={entry.mark} testId="otto-entry-mark" />;
  return (
    <span data-testid="otto-entry-mark" className="inline-block whitespace-nowrap rounded border border-slate-700 px-1.5 py-0.5 text-[11px] font-medium text-slate-300">
      {entry.mark}
    </span>
  );
}

/** One entry: a suggestion (one of Otto's proposals, with its page's own buttons), a next step (a button of a page,
 * under that button's own name), what a result means, or a line of a thread so far. */
function EntryCard({
  entry,
  compact,
  confirming,
  reason,
  onReason,
  sending,
  error,
  onAsk,
  onCancel,
  onConfirmDecision,
  onConfirmStep,
  who,
  name,
  onName,
}: {
  entry: AssistantEntry;
  compact: boolean;
  /** The key of this entry's button that is at its Confirm step, if any. */
  confirming: string | null;
  reason: string;
  onReason: (text: string) => void;
  sending: boolean;
  error: string | null;
  onAsk: (key: string) => void;
  onCancel: () => void;
  onConfirmDecision: (decision: AssistantDecision) => void;
  onConfirmStep: (step: AssistantStep) => void;
  /** Who a decision is recorded as; `ask`: the name is asked for now (once). */
  who: Who | null;
  name: string;
  onName: (text: string) => void;
}) {
  const proposal = entry.proposal;
  const step = entry.step;
  const decision = confirming && confirming !== "step" ? (entry.decisions.find((d) => d.key === confirming) ?? null) : null;
  const blocked = entry.decisions.filter((d) => !d.can && d.blocked_reason);
  return (
    <article
      data-testid="otto-entry"
      data-entry={entry.id}
      data-kind={entry.kind}
      data-what={entry.what}
      data-open-item={entry.open_item || undefined}
      className={`min-w-0 rounded-lg border bg-slate-900/70 ${compact ? "border-slate-800 p-2.5" : "border-slate-700 p-3"}`}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Mark entry={entry} />
        {entry.badge ? (
          entry.kind === "suggestion" ? (
            <ProposalStatusChip status={{ word: entry.badge.label, tone: entry.badge.tone }} testId="otto-entry-badge" />
          ) : entry.badge.label ? (
            <StatusChip label={entry.badge.label} tone={entry.badge.tone} size="sm" wrap testId="otto-entry-badge" />
          ) : null
        ) : null}
      </div>
      <p data-testid="otto-entry-title" className={`mt-1.5 break-words text-slate-100 ${compact ? "text-[13px]" : "font-medium"}`}>
        {entry.title}
      </p>
      {entry.text ? (
        <p data-testid="otto-entry-text" className={`mt-1 break-words text-slate-300 ${compact ? "text-xs" : "text-[13px]"}`}>
          {entry.text}
        </p>
      ) : null}
      {proposal?.decided_line && proposal.status.key !== "proposed" ? (
        <p data-testid="otto-entry-decided" className="mt-1 break-words text-xs text-slate-400">
          {proposal.decided_line}
        </p>
      ) : null}
      {entry.where || entry.links.length > 0 ? (
        <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {entry.where ? (
            <ItemLinkView link={entry.where.link} testId="otto-entry-where">
              {entry.where.label}
            </ItemLinkView>
          ) : null}
          {entry.links.map((link) => (
            <ItemLinkView key={link.label} link={link.link} testId="otto-entry-link">
              {link.label}
            </ItemLinkView>
          ))}
        </p>
      ) : null}

      {/* A suggestion's buttons: the page's own (Accept, Reject, Undo, Reconsider). Each first shows its Confirm step. */}
      {entry.decisions.length > 0 && !decision ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          {entry.decisions.map((d) =>
            d.key === "accept" ? (
              <PrimaryButton key={d.key} testId="otto-decision" disabled={!d.can || sending} onClick={() => onAsk(d.key)}>
                {d.label}
              </PrimaryButton>
            ) : (
              <SecondaryButton key={d.key} testId="otto-decision" disabled={!d.can || sending} onClick={() => onAsk(d.key)}>
                {d.label}
              </SecondaryButton>
            ),
          )}
        </div>
      ) : null}
      {blocked.length > 0 && !decision ? (
        <p data-testid="otto-blocked" className="mt-2 break-words text-xs text-slate-400">
          {Array.from(new Set(blocked.map((d) => d.blocked_reason))).join(" ")}
        </p>
      ) : null}
      {decision?.confirm ? (
        <ConfirmStep
          confirm={decision.confirm}
          reason={reason}
          onReason={onReason}
          sending={sending}
          error={error}
          onCancel={onCancel}
          onConfirm={() => onConfirmDecision(decision)}
          who={who}
          name={name}
          onName={onName}
        />
      ) : null}

      {/* A next step: the page button's own name. Opening a page needs no Confirm; everything else does. */}
      {step ? (
        step.needs === "nothing" && step.action.link ? (
          <p className="mt-2.5">
            <ItemLinkView
              link={step.action.link}
              testId="otto-step-open"
              className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-sm font-medium text-slate-100 hover:border-slate-500 hover:bg-slate-800"
            >
              {entry.title}
            </ItemLinkView>
          </p>
        ) : confirming === "step" && step.confirm ? (
          <ConfirmStep
            confirm={step.confirm}
            reason=""
            onReason={() => undefined}
            sending={sending}
            error={error}
            onCancel={onCancel}
            onConfirm={() => onConfirmStep(step)}
          />
        ) : (
          <>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <SecondaryButton testId="otto-step" disabled={!step.can || sending} onClick={() => onAsk("step")}>
                {entry.title}
              </SecondaryButton>
              {step.running ? (
                <span role="status" data-testid="otto-step-running" className="inline-flex items-center gap-1.5 text-xs text-slate-300">
                  <Spinner className="h-3.5 w-3.5" />
                  {step.progress ?? "Running"}
                </span>
              ) : null}
            </div>
            {!step.can && step.blocked_reason ? (
              <p data-testid="otto-blocked" className="mt-2 break-words text-xs text-slate-400">
                {step.blocked_reason}
              </p>
            ) : null}
          </>
        )
      ) : null}
    </article>
  );
}

/** The Confirm step: what will happen, what will not, which button of which page this presses; then Confirm or
 * Cancel. Nothing is sent before Confirm, and Cancel leaves everything as it was. */
function ConfirmStep({
  confirm,
  reason,
  onReason,
  sending,
  error,
  onCancel,
  onConfirm,
  who = null,
  name = "",
  onName,
}: {
  confirm: NonNullable<AssistantDecision["confirm"]>;
  reason: string;
  onReason: (text: string) => void;
  sending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
  /** A decision only: who it is recorded as. A next step records no name. */
  who?: Who | null;
  name?: string;
  onName?: (text: string) => void;
}) {
  const id = "otto-reason";
  return (
    <div data-testid="otto-confirm" role="group" aria-label={confirm.title} className="mt-2.5 rounded-lg border border-slate-600 bg-slate-950/60 p-2.5">
      <p className="text-[13px] font-semibold text-slate-100">{confirm.title}</p>
      <ul data-testid="otto-confirm-lines" className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-slate-300 marker:text-slate-500">
        {confirm.lines.map((line) => (
          <li key={line} className="break-words">
            {line}
          </li>
        ))}
      </ul>
      <p data-testid="otto-confirm-names" className="mt-1.5 text-xs text-slate-400">
        {confirm.names}
      </p>
      {confirm.reason ? (
        <div className="mt-2">
          <label htmlFor={id} className="block text-xs text-slate-400">
            {confirm.reason.label}
          </label>
          <input
            id={id}
            data-testid="otto-reason"
            type="text"
            value={reason}
            maxLength={confirm.reason.max}
            onChange={(e) => onReason(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
          />
        </div>
      ) : null}
      {who ? (
        who.ask ? (
          <div className="mt-2">
            <label htmlFor="otto-name" className="block text-xs text-slate-400">
              {who.ask_label}
            </label>
            <input
              id="otto-name"
              data-testid="otto-name"
              type="text"
              autoComplete="name"
              value={name}
              maxLength={who.max}
              onChange={(e) => onName?.(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
            />
            <p data-testid="otto-name-note" className="mt-1 break-words text-[11px] text-slate-500">
              {who.note}
            </p>
          </div>
        ) : (
          <p data-testid="otto-recorded-as" className="mt-1.5 text-xs text-slate-400">
            {who.line}
          </p>
        )
      ) : null}
      {error ? (
        <div className="mt-2">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <PrimaryButton testId="otto-confirm-button" busy={sending} onClick={onConfirm}>
          {confirm.confirm}
        </PrimaryButton>
        <SecondaryButton testId="otto-cancel-button" disabled={sending} onClick={onCancel}>
          {confirm.cancel}
        </SecondaryButton>
      </div>
    </div>
  );
}
