import { useEffect, useState } from "react";
import { api, errorMessage, type FixSection, type FixesView } from "../api";
import { FixList } from "./fixes/FixList";
import { FixSections } from "./fixes/FixSections";
import { FixSummary, type FixRequest } from "./fixes/FixSummary";
import { DemoDataLabel, ErrorBox } from "./ui";

const POLL_MS = 1000;

interface Props {
  planId: number;
  /** The fix to show. Without one, or when it is not in the list, the first fix is shown. */
  selectedId: string | null;
  onSelect: (fixId: string) => void;
  /** "Retest now" has started the retest: the app opens Evidence Lab, where it shows. */
  onRetestStarted: () => void;
}

/** The Fixes step. Every word, status and button comes from the backend; this screen works nothing out. */
export function FixesScreen({ planId, selectedId, onSelect, onRetestStarted }: Props) {
  const [view, setView] = useState<FixesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The sections the user opened or closed, by fix and section. The others keep the state the backend sent.
  const [toggled, setToggled] = useState<Readonly<Record<string, boolean>>>({});
  const [pollTick, setPollTick] = useState(0);

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
  }, [planId]);

  // While a proof (or anything else) runs, ask again every second. Not while a button's own call is
  // on its way: its answer is the newer view, and an older one must not land on top of it.
  const polling = view !== null && view.busy && !busy;
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
        <h1 id="fixes-title" className="text-xl font-semibold text-slate-50">
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
  const fix = current.fixes.find((f) => f.id === selectedId) ?? current.fixes[0];

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

  // The same retest as "Retest new version". Its progress and the before and after show in Evidence Lab.
  async function retest(fixId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.retestNow(current.plan_id, fixId);
      onRetestStarted();
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
    <section aria-labelledby="fixes-title">
      <div className="flex flex-wrap items-center gap-3">
        <h1 id="fixes-title" className="text-xl font-semibold text-slate-50">
          {current.title}
        </h1>
        {current.is_demo ? <DemoDataLabel /> : null}
      </div>
      <p data-testid="fixes-subline" className="mt-2 text-sm text-slate-400">
        {current.subline}
      </p>

      {error ? (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      <p data-testid="disclaimer" className="mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        {current.disclaimer}
      </p>

      {fix ? (
        <div className="mt-6 grid items-start gap-5 lg:grid-cols-[250px_1fr]">
          <FixList title={current.list_title} fixes={current.fixes} selectedId={fix.id} onSelect={onSelect} />
          <div className="flex min-w-0 flex-col gap-3">
            {/* The key gives each fix its own ticks and its own confirm box. */}
            <FixSummary key={fix.id} fix={fix} busy={busy} onRequest={(asked) => request(fix.id, asked)} />
            {fix.sections_note ? (
              <p data-testid="fix-sections-note" className="px-1 text-xs text-slate-400">
                {fix.sections_note}
              </p>
            ) : null}
            <FixSections
              sections={fix.sections}
              isOpen={(section) => toggled[sectionKey(fix.id, section)] ?? section.open}
              onToggle={(section) =>
                setToggled((prev) => {
                  const key = sectionKey(fix.id, section);
                  return { ...prev, [key]: !(prev[key] ?? section.open) };
                })
              }
            />
          </div>
        </div>
      ) : current.empty_text ? (
        <p data-testid="fixes-empty" className="mt-6 text-sm text-slate-400">
          {current.empty_text}
        </p>
      ) : null}
    </section>
  );
}
