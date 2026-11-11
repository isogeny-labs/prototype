import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, setUnauthorizedHandler, type Address, type Import, type Session, type VerifyRun } from "./api";
import { LoginScreen, SetupScreen } from "./components/AuthScreens";
import { CopilotPanel } from "./components/CopilotPanel";
import { ImportScreen } from "./components/ImportScreen";
import { VerifyScreen } from "./components/VerifyScreen";
import { ErrorBox, Wordmark } from "./components/ui";

type Step = "import" | "verify" | "tests";

function StepBar({
  step,
  canOpenVerify,
  onGo,
}: {
  step: Step;
  canOpenVerify: boolean;
  onGo: (step: Step) => void;
}) {
  const base = "flex flex-col items-start rounded-lg border px-3 py-2 text-left text-sm";
  const active = "border-sky-400/70 bg-sky-400/10 text-slate-50";
  const idle = "border-slate-800 text-slate-300 hover:border-slate-600";
  const off = "border-slate-800 text-slate-500 cursor-not-allowed";

  return (
    <nav aria-label="Steps">
      <ol className="flex flex-wrap items-stretch gap-2">
        <li>
          <button
            type="button"
            aria-current={step === "import" ? "step" : undefined}
            onClick={() => onGo("import")}
            className={`${base} ${step === "import" ? active : idle}`}
          >
            <span className="font-medium">1. Import</span>
          </button>
        </li>
        <li aria-hidden="true" className="self-center text-slate-600">
          →
        </li>
        <li>
          <button
            type="button"
            aria-current={step === "verify" ? "step" : undefined}
            disabled={!canOpenVerify}
            onClick={() => onGo("verify")}
            className={`${base} ${step === "verify" ? active : canOpenVerify ? idle : off}`}
          >
            <span className="font-medium">2. Verify</span>
          </button>
        </li>
        <li aria-hidden="true" className="self-center text-slate-600">
          →
        </li>
        <li>
          <button
            type="button"
            disabled
            aria-current={step === "tests" ? "step" : undefined}
            className={`${base} ${step === "tests" ? `${active} cursor-default` : off}`}
          >
            <span className="font-medium">3. Tests</span>
            <span className="text-xs">Coming in phase 2</span>
          </button>
        </li>
        <li aria-hidden="true" className="self-center text-slate-600">
          →
        </li>
        <li>
          <button type="button" disabled className={`${base} ${off}`}>
            <span className="font-medium">4. Evidence Lab</span>
            <span className="text-xs">Coming in phase 2</span>
          </button>
        </li>
      </ol>
    </nav>
  );
}

function TestsPlaceholder() {
  return (
    <section aria-labelledby="tests-title" className="space-y-2">
      <h1 id="tests-title" className="text-xl font-semibold text-slate-50">
        Tests
      </h1>
      <p className="text-sm text-slate-300">
        The Tests step arrives in phase 2. It isn't built yet, so nothing has been run here.
      </p>
      <p className="text-sm text-slate-400">Your import and the Verify results are still available from the steps above.</p>
    </section>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [imp, setImp] = useState<Import | null>(null);
  const [run, setRun] = useState<VerifyRun | null>(null);
  const [step, setStep] = useState<Step>("import");

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
      setImp(current);
      setRun(latest);
      setStep(latest ? "verify" : "import");
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

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-800 bg-slate-900/60">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3 sm:px-6">
          <Wordmark />
          <StepBar step={step} canOpenVerify={run !== null} onGo={setStep} />
        </div>
        <p className="border-t border-slate-800 bg-slate-900 px-4 py-1.5 text-xs text-slate-300 sm:px-6">
          Demo mode: running our own demo software, not isolated.
        </p>
      </header>

      <div className="flex flex-1 flex-col lg:flex-row">
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-5xl">
            {loadError ? (
              <div className="mb-4">
                <ErrorBox>{loadError}</ErrorBox>
              </div>
            ) : null}
            {step === "import" || (step === "verify" && (!imp || !run)) ? (
              <ImportScreen
                demoServer={session.demo_server}
                imp={imp}
                onImported={(next) => {
                  setImp(next);
                  setRun(null);
                }}
                onImportFailed={() => {
                  setImp(null);
                  setRun(null);
                }}
                onAddressChanged={onAddressChanged}
                onVerified={(next) => {
                  setRun(next);
                  setStep("verify");
                }}
              />
            ) : step === "verify" && imp && run ? (
              <VerifyScreen imp={imp} run={run} onContinue={() => setStep("tests")} />
            ) : (
              <TestsPlaceholder />
            )}
          </div>
        </main>
        <CopilotPanel />
      </div>
    </div>
  );
}
