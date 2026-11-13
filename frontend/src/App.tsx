import { Fragment, useCallback, useEffect, useState } from "react";
import { api, errorMessage, setUnauthorizedHandler, type Address, type Import, type PlanView, type Session, type VerifyRun } from "./api";
import { LoginScreen, SetupScreen } from "./components/AuthScreens";
import { CopilotPanel } from "./components/CopilotPanel";
import { EvidenceLabScreen } from "./components/EvidenceLabScreen";
import { FixesScreen } from "./components/FixesScreen";
import { ImportScreen } from "./components/ImportScreen";
import { TestsScreen } from "./components/TestsScreen";
import { VerifyScreen } from "./components/VerifyScreen";
import { ErrorBox, Wordmark } from "./components/ui";

type Step = "import" | "verify" | "tests" | "lab" | "fixes";

const STEP_KEY = "evidence-lab-step";

// Remembering the open step is only a convenience for a page refresh. If the
// browser won't store it, the app still works.
function rememberStep(step: Step) {
  try {
    window.sessionStorage.setItem(STEP_KEY, step);
  } catch {
    /* nothing to do */
  }
}

function rememberedStep(): string | null {
  try {
    return window.sessionStorage.getItem(STEP_KEY);
  } catch {
    return null;
  }
}

const STEPS: { step: Step; label: string }[] = [
  { step: "import", label: "1. Import" },
  { step: "verify", label: "2. Verify" },
  { step: "tests", label: "3. Tests" },
  { step: "lab", label: "4. Evidence Lab" },
  { step: "fixes", label: "5. Fixes" },
];

function StepBar({
  step,
  canOpen,
  onGo,
}: {
  step: Step;
  canOpen: Record<Step, boolean>;
  onGo: (step: Step) => void;
}) {
  const base = "flex flex-col items-start rounded-lg border px-3 py-2 text-left text-sm";
  const active = "border-sky-400/70 bg-sky-400/10 text-slate-50";
  const idle = "border-slate-800 text-slate-300 hover:border-slate-600";
  const off = "border-slate-800 text-slate-500 cursor-not-allowed";

  return (
    <nav aria-label="Steps">
      <ol className="flex flex-wrap items-stretch gap-2">
        {STEPS.map((item, i) => (
          <Fragment key={item.step}>
            {i > 0 ? (
              <li aria-hidden="true" className="self-center text-slate-600">
                →
              </li>
            ) : null}
            <li>
              <button
                type="button"
                aria-current={step === item.step ? "step" : undefined}
                disabled={!canOpen[item.step]}
                onClick={() => onGo(item.step)}
                className={`${base} ${step === item.step ? active : canOpen[item.step] ? idle : off}`}
              >
                <span className="font-medium">{item.label}</span>
              </button>
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [imp, setImp] = useState<Import | null>(null);
  const [run, setRun] = useState<VerifyRun | null>(null);
  const [plan, setPlan] = useState<PlanView | null>(null);
  const [step, setStep] = useState<Step>("import");
  // The fix that is open in the Fixes step. "View in Fixes" in Evidence Lab sets it.
  const [fixId, setFixId] = useState<string | null>(null);

  const go = useCallback((next: Step) => {
    setStep(next);
    rememberStep(next);
  }, []);

  // Loads the session, then whatever was already imported and checked, so a
  // page refresh keeps the user where they were.
  const refresh = useCallback(async () => {
    try {
      const s = await api.getSession();
      setLoadError(null);
      if (!s.logged_in) {
        setSession(s);
        return;
      }
      const current = await api.getCurrentImport();
      const latest = current ? await api.getLatestVerify(current.id) : null;
      const existingPlan = current ? await api.getPlan(current.id) : null;
      setImp(current);
      setRun(latest);
      setPlan(existingPlan);
      const wanted = rememberedStep();
      if ((wanted === "lab" || wanted === "fixes") && existingPlan?.has_results) setStep(wanted);
      else if (wanted === "tests" && current) setStep("tests");
      else if (wanted === "import") setStep("import");
      else setStep(latest ? "verify" : "import");
      setSession(s);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSession((s) => (s ? { ...s, logged_in: false } : s));
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        {loadError ? (
          <div className="max-w-md">
            <ErrorBox title="The app couldn't start">{loadError}</ErrorBox>
          </div>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </main>
    );
  }

  if (session.setup_required) return <SetupScreen onDone={() => void refresh()} />;
  if (!session.logged_in) return <LoginScreen onDone={() => void refresh()} />;

  function onAddressChanged(address: Address) {
    setImp((current) =>
      current
        ? { ...current, addresses: current.addresses.map((a) => (a.address === address.address ? address : a)) }
        : current,
    );
  }

  // A step whose data is gone (for example after a failed import) falls back to Import.
  // Fixes opens whenever Evidence Lab does: both need results.
  const hasResults = plan?.has_results === true;
  const shown: Step =
    (step === "verify" && imp && run) || (step === "tests" && imp) || ((step === "lab" || step === "fixes") && imp && hasResults)
      ? step
      : "import";

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-800 bg-slate-900/60">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3 sm:px-6">
          <Wordmark />
          <StepBar
            step={shown}
            canOpen={{ import: true, verify: run !== null, tests: imp !== null, lab: hasResults, fixes: hasResults }}
            onGo={go}
          />
        </div>
        {session.mode_line ? (
          <p data-testid="mode-line" className="border-t border-slate-800 bg-slate-900 px-4 py-1.5 text-xs text-slate-300 sm:px-6">
            {session.mode_line}
          </p>
        ) : null}
      </header>

      <div className="flex flex-1 flex-col lg:flex-row">
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-5xl">
            {loadError ? (
              <div className="mb-4">
                <ErrorBox>{loadError}</ErrorBox>
              </div>
            ) : null}
            {shown === "import" ? (
              <ImportScreen
                demoServer={session.demo_server}
                imp={imp}
                onImported={(next) => {
                  setImp(next);
                  setRun(null);
                  setPlan(null);
                  // A new file has its own fixes: the fix picked for the file before is not carried over.
                  setFixId(null);
                }}
                onImportFailed={() => {
                  setImp(null);
                  setRun(null);
                  setPlan(null);
                  setFixId(null);
                }}
                onAddressChanged={onAddressChanged}
                onVerified={(next) => {
                  setRun(next);
                  go("verify");
                }}
              />
            ) : shown === "verify" && imp && run ? (
              <VerifyScreen imp={imp} run={run} onContinue={() => go("tests")} />
            ) : shown === "tests" && imp ? (
              <TestsScreen importId={imp.id} plan={plan} onPlan={setPlan} />
            ) : shown === "lab" && plan ? (
              <EvidenceLabScreen
                planId={plan.id}
                onViewFix={(id) => {
                  setFixId(id);
                  go("fixes");
                }}
              />
            ) : shown === "fixes" && plan ? (
              <FixesScreen planId={plan.id} selectedId={fixId} onSelect={setFixId} onRetestStarted={() => go("lab")} />
            ) : null}
          </div>
        </main>
        <CopilotPanel />
      </div>
    </div>
  );
}
