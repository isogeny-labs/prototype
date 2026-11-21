import { useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, errorMessage, type Session } from "../api";
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

/** Hosting: log in with the GitHub App. A plain link: the server sends the browser on to GitHub and back. */
function GitHubLogin() {
  return (
    <a
      href="/api/auth/github/start"
      className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-700"
    >
      <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-current">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
      </svg>
      Log in with GitHub
    </a>
  );
}

export function LoginScreen({ onDone, methods }: { onDone: () => void; methods?: Session["login"] }) {
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

  const github = methods?.github ?? false;
  const passwordOn = methods?.password ?? true;
  const intro = passwordOn
    ? github
      ? "Log in with your GitHub account, or type the password created for this app."
      : "Type the password you created for this app."
    : "Log in with your GitHub account.";

  return (
    <AuthCard title="Log in" intro={intro}>
      {github ? <GitHubLogin /> : null}
      {passwordOn ? (
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
      ) : null}
    </AuthCard>
  );
}
