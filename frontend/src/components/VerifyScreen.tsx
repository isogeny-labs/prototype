import { useState } from "react";
import type { Evidence, Import, Result, ResultValue, VerifyRun } from "../api";
import { DemoDataLabel, PrimaryButton, SourceTag } from "./ui";

// "True" only means the claim matched what we measured, so it is styled as a
// neutral match, not as "safe". Every badge carries its text and a symbol, so
// nothing depends on colour alone.
const BADGES: Record<ResultValue, { symbol: string; className: string; meaning: string }> = {
  True: {
    symbol: "=",
    className: "border-sky-400/60 bg-sky-400/10 text-sky-100",
    meaning: "The claim matches what we measured.",
  },
  False: {
    symbol: "≠",
    className: "border-amber-400/70 bg-amber-400/15 text-amber-100",
    meaning: "The claim doesn't match what we measured.",
  },
  "Couldn't check": {
    symbol: "?",
    className: "border-slate-500 bg-slate-700/40 text-slate-100",
    meaning: "We couldn't measure this, so there is no answer.",
  },
};

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function EvidenceItem({ item }: { item: Evidence }) {
  return (
    <li className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <p className="text-sm font-medium text-slate-100">{item.title}</p>
      <dl className="mt-2 space-y-2 text-xs">
        <div>
          <dt className="text-slate-500">Command</dt>
          <dd>
            <code className="block whitespace-pre-wrap break-words font-mono text-slate-200">{item.command}</code>
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Raw output</dt>
          <dd>
            <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-900 p-2 font-mono text-slate-200">
              {item.output}
            </pre>
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          <div>
            <dt className="inline text-slate-500">Time: </dt>
            <dd className="inline text-slate-300">
              <time dateTime={item.started_at}>{formatTime(item.started_at)}</time>
            </dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Duration: </dt>
            <dd className="inline text-slate-300">
              {item.duration_ms} ms <SourceTag>measured</SourceTag>
            </dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Tool: </dt>
            <dd className="inline text-slate-300">
              {item.tool} {item.tool_version}
            </dd>
          </div>
        </div>
      </dl>
    </li>
  );
}

function ResultRow({ result }: { result: Result }) {
  const [open, setOpen] = useState(false);
  const badge = BADGES[result.result];
  const evidenceId = `evidence-${result.claim_id}`;

  return (
    <li data-testid="result-row" className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="grid gap-4 md:grid-cols-[1fr_1fr_13rem]">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Claim</p>
          <p className="mt-1 text-sm text-slate-100">{result.claim.text}</p>
          <p className="mt-1.5">
            <SourceTag>from the file</SourceTag>
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">What we found</p>
          <p className="mt-1 text-sm text-slate-100">{result.found}</p>
          <p className="mt-1.5">
            <SourceTag>measured</SourceTag>
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Result</p>
          <p
            className={`mt-1 inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-semibold ${badge.className}`}
          >
            <span aria-hidden="true" className="font-mono">
              {badge.symbol}
            </span>
            <span data-testid="result-badge">{result.result}</span>
          </p>
          <p className="mt-1.5 text-xs text-slate-400">
            {result.result === "Couldn't check" && result.reason ? result.reason : badge.meaning}
          </p>
        </div>
      </div>

      <div className="mt-3 border-t border-slate-800 pt-3">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={evidenceId}
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 rounded text-sm text-slate-300 hover:text-slate-100"
        >
          <span aria-hidden="true" className="font-mono text-xs">
            {open ? "▾" : "▸"}
          </span>
          Evidence
        </button>
        {open ? (
          <div id={evidenceId} className="mt-3">
            {result.evidence.length === 0 ? (
              <p className="text-sm text-slate-400">Nothing was run for this claim, so there is no raw output.</p>
            ) : (
              <ul className="space-y-3">
                {result.evidence.map((item, i) => (
                  <EvidenceItem key={i} item={item} />
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>
    </li>
  );
}

interface Props {
  imp: Import;
  run: VerifyRun;
  onContinue: () => void;
}

export function VerifyScreen({ imp, run, onContinue }: Props) {
  return (
    <section aria-labelledby="verify-title" className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="verify-title" className="text-xl font-semibold text-slate-50">
            Verify
          </h1>
          {imp.is_demo ? <DemoDataLabel /> : null}
        </div>
        <p className="mt-1 text-sm text-slate-400">
          Each claim from {imp.filename}, checked against the real system. Checked{" "}
          <time dateTime={run.finished_at}>{formatTime(run.finished_at)}</time>.
        </p>
      </div>

      {run.results.length === 0 ? (
        <p className="text-sm text-slate-400">There were no claims to check.</p>
      ) : (
        <ul className="space-y-3">
          {run.results.map((result) => (
            <ResultRow key={result.claim_id} result={result} />
          ))}
        </ul>
      )}

      <p className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        Passing these tests doesn't prove a system secure. It shows these specific checks passed.
      </p>

      <div>
        <PrimaryButton onClick={onContinue}>Continue to tests</PrimaryButton>
      </div>
    </section>
  );
}
