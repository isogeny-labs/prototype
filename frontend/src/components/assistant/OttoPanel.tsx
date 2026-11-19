import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import {
  api,
  errorMessage,
  type AssistantDecision,
  type AssistantEntry,
  type AssistantFact,
  type AssistantGo,
  type AssistantReply,
  type AssistantStep,
  type AssistantTab,
  type AssistantThread,
  type AssistantView,
} from "../../api";
import { fromPanel, onChanged, useChangeStamp } from "../../changes";
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
  /** Where the card is: a decided suggestion that can still be undone is listed twice (on this page, and in its thread
   * so far), and only the card whose button was pressed shows the Confirm step. */
  place: Place;
}

/** "reply": the card that came back for a typed sentence (phase 6b). */
type Place = "page" | "thread" | "reply";

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
  onGoTo,
}: {
  assessmentId: number;
  page: Page;
  /** The item open on the page (its side panel), if any. */
  item: string | null;
  /** Opens a page of this assessment, as the page itself does after its button's answer. */
  onGo: (page: Page, item?: string | null) => void;
  /** Phase 6b: where an answer to a typed sentence leads (a page, an item, the filters of its table; or Settings). */
  onGoTo?: (where: AssistantGo) => void;
}) {
  const [view, setView] = useState<AssistantView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // (how many reads have come back, answered or failed: the next one is timed from there)
  const [answered, setAnswered] = useState(0);
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
      })
      .finally(() => {
        if (asked.current === mine) setAnswered((n) => n + 1);
      });
  }, [assessmentId, page, item, changed, tick]);

  // While something runs, ask again (the page does the same for its own view). A read that failed is asked again
  // too: one lost answer must not leave a card saying "running" for good.
  const busy = view?.busy === true && view.assessment_id === assessmentId;
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [busy, answered]);

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
  // A closed tab that came back (something new happened in its thread) is open again for good: it is not hidden a
  // second time when its thread later reads as it did when the tab was closed (a proof that fails, runs, fails again).
  const returned = (current?.tabs ?? []).filter((t) => t.key in tabPrefs.closed && tabPrefs.closed[t.key] !== t.mark).map((t) => t.key).join(",");
  useEffect(() => {
    if (!returned) return;
    const back = returned.split(",");
    saveTabs((now) => {
      const closed = { ...now.closed };
      for (const key of back) delete closed[key];
      return { ...now, closed };
    });
  }, [returned, saveTabs]);
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
  // ---- phase 6b: the text box. What was typed last and what came back for it; nothing of it is sent on by itself.
  const [typed, setTyped] = useState("");
  const [asking, setAsking] = useState(false);
  const [exchange, setExchange] = useState<{ said: string; reply: AssistantReply; confirmed: boolean; stale?: boolean } | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const boxId = useId();
  useEffect(() => {
    setExchange(null);
    setAskError(null);
  }, [assessmentId]);
  // The card that came back for a sentence shows the suggestion or the button as it stood when the sentence was
  // answered. Once anything changes the assessment after that (a decision on its page, another card's Confirm), the
  // card is taken away and a line says so: a button in the panel must never stand where its page's button no longer
  // does. (The reply card's own Confirm is not such a change: it ends in "Confirmed.".)
  const confirmingReply = useRef(false);
  useEffect(
    () =>
      onChanged(() => {
        if (confirmingReply.current) return;
        setExchange((now) => (now && now.reply.entry && !now.confirmed ? { ...now, stale: true } : now));
      }),
    [],
  );
  // Who a decision is recorded as. A name is asked for once, at the first Confirm of a decision (and kept in Settings).
  const [name, setName] = useState("");
  const [nameAsked, setNameAsked] = useState(prefs.ottoNameAsked);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  useEffect(() => {
    setConfirming(null);
    setSendError(null);
  }, [page, assessmentId]);

  function ask(entry: AssistantEntry, key: string, place: Place) {
    setConfirming({ entry: entry.id, key, place });
    setReason("");
    setSendError(null);
  }

  function cancel() {
    setConfirming(null);
    setReason("");
    setSendError(null);
  }

  async function confirm(send: () => Promise<unknown>, then?: { page: string; item: string | null } | null) {
    setSending(true);
    setSendError(null);
    confirmingReply.current = confirming?.place === "reply";
    try {
      await fromPanel(send);
      // (the card that came back for a typed sentence has done its work: the page and the thread show what it led to)
      if (confirming?.place === "reply") setExchange((now) => (now ? { ...now, confirmed: true } : now));
      setConfirming(null);
      setReason("");
      if (then) onGo(then.page as Page, then.item);
    } catch (e) {
      setSendError(errorMessage(e));
    } finally {
      confirmingReply.current = false;
      setSending(false);
    }
  }

  const planId = current?.plan_id ?? null;

  /** Phase 6b: one typed sentence. The answer either takes the app somewhere (moving around is done at once) or is a
   * card whose Confirm step is shown; nothing is decided or started by sending. In an open assessment the exchange is
   * kept with it; in a closed one, or before a file is in, it is answered and not kept. */
  async function say(text: string) {
    const words = text.trim();
    if (!words || asking || !current) return;
    setAsking(true);
    setAskError(null);
    try {
      const reply = current.box.kept && planId !== null ? await api.say(planId, page, item, words) : await api.getAnswer(assessmentId, page, item, words);
      setTyped("");
      setExchange({ said: words, reply, confirmed: false });
      setConfirming(null);
      setSendError(null);
      setReason(reply.open?.reason ?? "");
      if (reply.kind === "tab" && reply.tab) {
        if (reply.tab.how === "close") {
          const tab = (current.tabs ?? []).find((t) => t.key === reply.tab!.thread);
          if (tab) closeTab(tab);
        } else {
          reopen(reply.tab.thread);
          setPicked(reply.tab.thread);
        }
      }
      if ((reply.kind === "went" || reply.kind === "page_only") && reply.go) onGoTo?.(reply.go);
      if (reply.kind === "card" && reply.entry && reply.open) setConfirming({ entry: reply.entry.id, key: reply.open.key, place: "reply" });
    } catch (e) {
      setAskError(errorMessage(e));
    } finally {
      setAsking(false);
    }
  }

  // A Confirm step whose button a new read turned off (or whose card is gone) is closed: the card then shows the
  // button again, off, with the page's own reason. Not while its request is on its way.
  const pageEntries = current?.on_page.entries;
  const threadEntries = selected?.so_far;
  const replyEntry = exchange && !exchange.stale ? exchange.reply.entry : null;
  useEffect(() => {
    if (!confirming || sending) return;
    if (confirming.place === "reply") {
      if (!replyEntry || replyEntry.id !== confirming.entry) setConfirming(null);
      return;
    }
    const entry = (confirming.place === "page" ? pageEntries : threadEntries)?.find((e) => e.id === confirming.entry);
    const still = confirming.key === "step" ? entry?.step?.confirm : entry?.decisions.find((d) => d.key === confirming.key)?.confirm;
    if (!still) {
      setConfirming(null);
      setReason("");
    }
  }, [confirming, sending, pageEntries, threadEntries, replyEntry]);
  const card = (entry: AssistantEntry, compact = false, where: Place | null = null) => {
    const place: Place = where ?? (compact ? "thread" : "page");
    const mine = confirming?.entry === entry.id && confirming.place === place;
    return (
    <EntryCard
      key={entry.id}
      entry={entry}
      compact={compact}
      confirming={mine ? confirming.key : null}
      reason={reason}
      onReason={setReason}
      sending={sending}
      error={mine ? sendError : null}
      onAsk={(key) => ask(entry, key, place)}
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
      onConfirmStep={(step) => void confirm(() => sendStep(step.action), pageAfter(step.action))}
    />
    );
  };

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

          {/* Phase 6b: what was typed last and what came back for it, then the text box with its example chips. */}
          {exchange ? (
            <section data-testid="otto-reply" data-kind={exchange.reply.kind} aria-label="The answer" className="rounded-lg border border-slate-700 bg-slate-950/40 p-3">
              <p data-testid="otto-reply-said" className="break-words text-xs text-slate-400">
                You said: <span className="text-slate-200">{exchange.said}</span>
              </p>
              <p data-testid="otto-reply-text" role="status" className="mt-1.5 break-words text-[13px] text-slate-100">
                {exchange.reply.text}
              </p>
              {/* Phase 6c: a fixed question's answer: where it is from, then its facts, each with the link to where it is shown. */}
              {exchange.reply.label ? (
                <p data-testid="otto-reply-label" className="mt-1 text-[11px] uppercase tracking-wider text-slate-500">
                  {exchange.reply.label}
                </p>
              ) : null}
              <Facts facts={exchange.reply.facts ?? []} />
              {exchange.reply.entry && !exchange.confirmed && !exchange.stale ? <div className="mt-2.5">{card(exchange.reply.entry, false, "reply")}</div> : null}
              {exchange.reply.entry && !exchange.confirmed && exchange.stale ? (
                <p data-testid="otto-reply-stale" className="mt-1.5 text-xs text-slate-400">
                  Something has changed in this assessment since this answer, so its card is no longer shown. Say it again to see where it stands
                  now.
                </p>
              ) : null}
              {exchange.confirmed ? (
                <p data-testid="otto-reply-confirmed" className="mt-1.5 text-xs text-slate-400">
                  Confirmed. The request the page's own button sends was sent.
                </p>
              ) : null}
              {exchange.reply.options.length > 0 ? (
                <ul data-testid="otto-reply-options" className="mt-2 space-y-1.5">
                  {exchange.reply.options.map((option, n) => (
                    <li key={`${n}-${option.say}`}>
                      <button
                        type="button"
                        data-testid="otto-reply-option"
                        disabled={asking}
                        onClick={() => void say(option.say)}
                        className="w-full break-words rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-left text-[13px] text-slate-100 hover:border-slate-500 disabled:opacity-50"
                      >
                        {option.label}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {exchange.reply.can.length > 0 ? (
                <ul data-testid="otto-reply-can" className="mt-2 space-y-1">
                  {exchange.reply.can.map((line) => (
                    <li key={line.say} className="break-words text-xs text-slate-400">
                      {/* (an example: it goes into the box to be changed, and is sent only by Send) */}
                      <button
                        type="button"
                        data-testid="otto-reply-example"
                        onClick={() => {
                          setTyped(line.say);
                          boxRef.current?.focus({ preventScroll: true });
                        }}
                        className="text-left text-sky-300 underline-offset-2 hover:underline"
                      >
                        {line.say}
                      </button>
                      <span className="text-slate-500"> {line.about}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}
          <form
            data-testid="otto-box"
            className="border-t border-slate-800 pt-3"
            onSubmit={(e) => {
              e.preventDefault();
              void say(typed);
            }}
          >
            {current.box.questions.length > 0 ? (
              <div data-testid="otto-questions" className="mb-2 flex flex-wrap gap-1.5">
                {current.box.questions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    data-testid="otto-question"
                    disabled={asking}
                    onClick={() => void say(question)}
                    className="rounded-full border border-sky-800/70 bg-sky-950/40 px-2.5 py-1 text-left text-xs text-sky-100 hover:border-sky-600 disabled:opacity-50"
                  >
                    {question}
                  </button>
                ))}
              </div>
            ) : null}
            <div data-testid="otto-chips" className="mb-2 flex flex-wrap gap-1.5">
              {current.box.chips.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  data-testid="otto-chip"
                  disabled={asking}
                  onClick={() => void say(chip)}
                  className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 hover:border-slate-500 disabled:opacity-50"
                >
                  {chip}
                </button>
              ))}
            </div>
            <label htmlFor={boxId} className="block text-xs text-slate-400">
              {current.box.label}
            </label>
            <div className="mt-1 flex items-end gap-2">
              <textarea
                id={boxId}
                ref={boxRef}
                data-testid="otto-box-text"
                rows={2}
                value={typed}
                maxLength={current.box.max}
                onChange={(e) => setTyped(e.target.value)}
                onKeyDown={(e) => {
                  // Enter sends; Shift+Enter makes a new line.
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void say(typed);
                  }
                }}
                className="min-w-0 flex-1 resize-none rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
              />
              <SecondaryButton testId="otto-box-send" allowWhenClosed disabled={asking || typed.trim() === ""} onClick={() => void say(typed)}>
                {current.box.send}
              </SecondaryButton>
            </div>
            {current.box.kept_note ? (
              <p data-testid="otto-box-note" className="mt-1.5 break-words text-[11px] text-slate-500">
                {current.box.kept_note}
              </p>
            ) : null}
            {askError ? (
              <div className="mt-2">
                <ErrorBox>{askError}</ErrorBox>
              </div>
            ) : null}
          </form>

          <p data-testid="otto-note" className="border-t border-slate-800 pt-3 text-xs text-slate-500">
            {current.note}
          </p>
        </div>
      ) : null}
    </aside>
  );
}

/** Phase 6c: the facts of an answer to a fixed question. Each is a sentence the app already shows about the item, with
 * the link to where it is shown. Nothing here is the panel's own judgement, and nothing can be pressed but a link. */
function Facts({ facts, compact = false }: { facts: AssistantFact[]; compact?: boolean }) {
  if (facts.length === 0) return null;
  return (
    <ol data-testid="otto-facts" className={`mt-2 list-decimal space-y-1.5 pl-5 marker:text-slate-500 ${compact ? "text-xs" : "text-[13px]"}`}>
      {facts.map((fact, n) => (
        <li key={`${n}-${fact.text}`} data-testid="otto-fact" className="break-words text-slate-200">
          {fact.text}
          {fact.link ? (
            <>
              {" "}
              <ItemLinkView link={fact.link} testId="otto-fact-link" className="whitespace-nowrap text-xs text-sky-300 underline-offset-2 hover:underline">
                {fact.label ?? "Open"}
              </ItemLinkView>
            </>
          ) : null}
        </li>
      ))}
    </ol>
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
  // (only a button that can be confirmed has a Confirm step: one a new read turned off shows as a button again, with its reason)
  const found = confirming && confirming !== "step" ? (entry.decisions.find((d) => d.key === confirming) ?? null) : null;
  const decision = found?.confirm ? found : null;
  const blocked = entry.decisions.filter((d) => !d.can && d.blocked_reason);
  // When the Confirm step closes (Cancel, or its request is answered), the keyboard's place goes back to the button
  // that opened it, where that button is still on the card. Opening the step moved it into the step.
  const article = useRef<HTMLElement>(null);
  const opened = useRef<string | null>(null);
  useEffect(() => {
    const before = opened.current;
    opened.current = confirming;
    if (before === null || confirming !== null) return;
    const root = article.current;
    const active = document.activeElement;
    if (!root || (active !== null && active !== document.body && !root.contains(active))) return; // the person is elsewhere by now
    const buttons =
      before === "step"
        ? root.querySelectorAll<HTMLButtonElement>('[data-testid="otto-step"]')
        : root.querySelectorAll<HTMLButtonElement>('[data-testid="otto-decision"]');
    const index = before === "step" ? 0 : Math.max(0, entry.decisions.findIndex((d) => d.key === before));
    (buttons[index] ?? buttons[0])?.focus({ preventScroll: true });
  }, [confirming, entry.decisions]);
  return (
    <article
      ref={article}
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
      <Facts facts={entry.facts ?? []} compact />
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
  const id = useId();
  const nameId = useId();
  // Opening the step takes the pressed button off the card: the keyboard's place moves to the step, which says what
  // will happen, and from there Tab reaches the field, Confirm and Cancel.
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.focus({ preventScroll: true });
  }, []);
  return (
    <div
      ref={box}
      tabIndex={-1}
      data-testid="otto-confirm"
      role="group"
      aria-label={confirm.title}
      className="mt-2.5 rounded-lg border border-slate-600 bg-slate-950/60 p-2.5 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
    >
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
            <label htmlFor={nameId} className="block text-xs text-slate-400">
              {who.ask_label}
            </label>
            <input
              id={nameId}
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
