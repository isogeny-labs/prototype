import { useCallback, useState } from "react";
import type { Evidence, Import, Result, ResultValue, Tone, VerifyRun } from "../api";
import { DataTable, DetailPanel, PageHeader, TableWithPanel, type Column } from "./layout";
import { AlsoNoticedList, DemoDataLabel, PrimaryButton, ResultBadge, SourceTag } from "./ui";

// "True" only means the claim matched what we measured, so it is drawn as a calm match, not as "safe". The chip
// carries its words and a symbol, so nothing depends on colour alone.
const BADGES: Record<ResultValue, { tone: Tone; meaning: string }> = {
  True: { tone: "pass", meaning: "The claim matches what we measured." },
  False: { tone: "fail", meaning: "The claim doesn't match what we measured." },
  "Couldn't check": { tone: "warn", meaning: "We couldn't measure this, so there is no answer." },
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

/** What opens in the panel: what we found, what the result means, and the raw evidence. */
function ResultDetails({ result }: { result: Result }) {
  const badge = BADGES[result.result];
  return (
    <div id={`details-${result.claim_id}`} className="space-y-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Claim</p>
        <p className="mt-1 text-sm text-slate-300">
          {result.claim.text} <SourceTag>from the file</SourceTag>
        </p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">What we found</p>
        <p className="mt-1 text-sm text-slate-200">
          {result.found} <SourceTag>measured</SourceTag>
        </p>
        <p className="mt-1.5 text-xs text-slate-400">
          {result.result === "Couldn't check" && result.reason ? result.reason : badge.meaning}
        </p>
      </div>
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
  );
}

interface Props {
  imp: Import;
  run: VerifyRun;
  onContinue: () => void;
}

export function VerifyScreen({ imp, run, onContinue }: Props) {
  const [openId, setOpenId] = useState<number | null>(null);
  const close = useCallback(() => setOpenId(null), []);
  const toggle = (id: number) => setOpenId((cur) => (cur === id ? null : id));
  const selected = run.results.find((r) => r.claim_id === openId) ?? null;

  const columns: Column<Result>[] = [
    {
      key: "claim",
      header: "Claim",
      render: (r) => (
        <div className="min-w-0">
          <p className="text-sm text-slate-300">
            {r.claim.text} <SourceTag>from the file</SourceTag>
          </p>
          <p data-testid="verify-summary" className="mt-2 text-sm text-slate-100">
            {r.summary}
          </p>
          {r.also_noticed.length > 0 ? (
            <div className="mt-2">
              <AlsoNoticedList title="Also noticed" items={r.also_noticed} />
            </div>
          ) : null}
        </div>
      ),
    },
    { key: "result", header: "Result", className: "w-44", render: (r) => <ResultBadge label={r.result} tone={BADGES[r.result].tone} /> },
    {
      key: "details",
      header: <span className="sr-only">Details</span>,
      className: "w-52",
      render: (r) => {
        const open = r.claim_id === openId;
        return (
          <button
            type="button"
            data-testid="verify-details-toggle"
            aria-expanded={open}
            aria-controls={`details-${r.claim_id}`}
            onClick={(e) => {
              e.stopPropagation();
              toggle(r.claim_id);
            }}
            className="flex items-center gap-2 rounded text-sm text-slate-300 hover:text-slate-100"
          >
            <span aria-hidden="true" className="font-mono text-xs">
              {open ? "▾" : "▸"}
            </span>
            Details and evidence
          </button>
        );
      },
    },
  ];

  const table =
    run.results.length === 0 ? (
      <p className="text-sm text-slate-400">There were no claims to check.</p>
    ) : (
      <DataTable
        label="Claims and results"
        columns={columns}
        rows={run.results}
        rowKey={(r) => String(r.claim_id)}
        rowTestId="result-row"
        selectedKey={selected ? String(selected.claim_id) : null}
        onRowClick={(r) => toggle(r.claim_id)}
      />
    );

  return (
    <section aria-label="Verify" className="space-y-6">
      <PageHeader
        eyebrow={imp.is_demo ? <DemoDataLabel /> : undefined}
        title="Verify"
        description={
          <>
            Each claim from {imp.filename}, checked against the real system. Checked{" "}
            <time dateTime={run.finished_at}>{formatTime(run.finished_at)}</time>.
          </>
        }
      />

      <TableWithPanel
        panelOpen={selected !== null}
        table={table}
        panel={
          <DetailPanel
            open={selected !== null}
            title={selected ? selected.claim.text : ""}
            subtitle={selected ? <ResultBadge label={selected.result} tone={BADGES[selected.result].tone} /> : undefined}
            onClose={close}
          >
            {selected ? <ResultDetails result={selected} /> : null}
          </DetailPanel>
        }
      />

      <p className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300">
        Passing these tests doesn't prove a system secure. It shows these specific checks passed.
      </p>

      <div>
        <PrimaryButton allowWhenClosed onClick={onContinue}>
          Continue to tests
        </PrimaryButton>
      </div>
    </section>
  );
}
