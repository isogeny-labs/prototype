import { useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, errorMessage } from "../api";
import { ErrorBox, PrimaryButton, Wordmark } from "./ui";

const MIN_PASSWORD_LENGTH = 8;

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 placeholder:text-slate-500";

function AuthCard({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <Wordmark large />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h1 className="text-lg font-semibold text-slate-50">{title}</h1>
          <p className="mt-1 text-sm text-slate-400">{intro}</p>
          {children}
        </div>
      </div>
    </main>
  );
}

/** First run only: the user chooses the password for this computer. */
export function SetupScreen({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Please use at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== repeat) {
      setError("The two passwords don't match. Please type them again.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.setup(password);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Create your password"
      intro="This is the first time the app has been opened. Choose a password to protect it on this computer. You'll use it to log in from now on."
    >
      <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
        <label className="block text-sm text-slate-300">
          Password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
            aria-describedby="password-hint"
          />
        </label>
        <p id="password-hint" className="-mt-2 text-xs text-slate-500">
          At least {MIN_PASSWORD_LENGTH} characters.
        </p>
        <label className="block text-sm text-slate-300">
          Repeat password
          <input
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            className={inputClass}
          />
        </label>
        {error ? <ErrorBox>{error}</ErrorBox> : null}
        <PrimaryButton type="submit" busy={busy}>
          Create password
        </PrimaryButton>
      </form>
    </AuthCard>
  );
}

export function LoginScreen({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password.length === 0) {
      setError("Please type your password.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.login(password);
      onDone();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "That password isn't right. Please try again."
          : errorMessage(err),
      );
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Log in" intro="Type the password you created for this app.">
      <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
        <label className="block text-sm text-slate-300">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </label>
        {error ? <ErrorBox>{error}</ErrorBox> : null}
        <PrimaryButton type="submit" busy={busy}>
          Log in
        </PrimaryButton>
      </form>
    </AuthCard>
  );
}
