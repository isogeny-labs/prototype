import { useEffect, useState } from "react";
import { api, errorMessage, type EvidenceExport, type EvidenceFileRow, type EvidenceFilesView } from "../../api";
import { DownloadStatus, downloadEvidence } from "../evidenceDownload";
import { DataTable, PageHeader, type Column } from "../layout";
import { DemoDataLabel, ErrorBox, SecondaryButton, formatTime, saveFile } from "../ui";
import { EVIDENCE_EYEBROW, NamesNote, Who } from "./parts";

/** The design refactor (26 November 2026): Evidence files, the fourth view of Evidence. Every download of the signed
 * evidence file with its time, its fingerprint and who downloaded it; Download evidence (the same button and the same
 * request as on Results); how to check a file with the verify command; and what the file holds. */
export function EvidenceFilesPage({ planId }: { planId: number }) {
  const [view, setView] = useState<EvidenceFilesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exported, setExported] = useState<EvidenceExport | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api
      .getEvidenceFiles(planId)
      .then((next) => {
        if (live) setView(next);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId, tick]);

  if (!view) {
    return error ? (
      <ErrorBox title="The evidence files couldn't be loaded">{error}</ErrorBox>
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  }

  async function download() {
    setBusy(true);
    setError(null);
    try {
      setExported(await downloadEvidence(planId));
      setTick((n) => n + 1); // the list now holds this download
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<EvidenceFileRow>[] = [
    {
      key: "when",
      header: "Downloaded",
      minWidth: 170,
      render: (row) => (
        <time dateTime={row.at} className="text-[13px] tabular-nums text-slate-200">
          {formatTime(row.at)}
        </time>
      ),
    },
    {
      key: "fingerprint",
      header: view.files[0]?.fingerprint_label ?? "Fingerprint",
      minWidth: 220,
      render: (row) => (
        <span data-testid="file-fingerprint" className="break-all font-mono text-xs text-slate-300">
          {row.fingerprint}
        </span>
      ),
    },
    { key: "who", header: "Who", minWidth: 130, render: (row) => <Who who={row.who} testId="file-who" /> },
    {
      key: "files",
      header: "Files",
      minWidth: 160,
      render: (row) => (
        <span className="flex flex-wrap gap-x-3 gap-y-1 text-[13px]">
          <button
            type="button"
            data-testid="file-json"
            onClick={() => saveFile(row.json.url, row.json.filename)}
            className="text-sky-300 hover:underline"
          >
            The signed file (.json)
          </button>
          <button
            type="button"
            data-testid="file-html"
            onClick={() => saveFile(row.html.url, row.html.filename)}
            className="text-sky-300 hover:underline"
          >
            The report
          </button>
        </span>
      ),
    },
  ];

  return (
    <section aria-label={view.title} data-testid="evidence-files-page">
      <PageHeader
        eyebrow={
          <>
            {EVIDENCE_EYEBROW}
            {view.is_demo ? (
              <>
                {" "}
                <DemoDataLabel />
              </>
            ) : null}
          </>
        }
        title={view.title}
        description={<span data-testid="evidence-files-subline">{view.subline}</span>}
        actions={
          <SecondaryButton allowWhenClosed disabled={busy || !view.download.can_start} onClick={() => void download()}>
            Download evidence
          </SecondaryButton>
        }
      />
      {error ? (
        <div className="mb-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      {!view.download.can_start && view.download.blocked_reason ? (
        <p data-testid="download-blocked" className="mb-3 text-sm text-slate-400">
          {view.download.blocked_reason}
        </p>
      ) : null}
      {exported ? <DownloadStatus exported={exported} /> : null}

      <div className="mt-4">
        {view.files.length === 0 ? (
          <p
            data-testid="evidence-files-empty"
            className="rounded-xl border border-slate-800 px-4 py-8 text-center text-sm text-slate-400"
          >
            {view.empty_text}
          </p>
        ) : (
          <DataTable
            label="Downloads of the evidence file"
            columns={columns}
            rows={view.files}
            rowKey={(row) => String(row.id)}
            rowTestId="evidence-file-row"
          />
        )}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section
          aria-label={view.check.title}
          data-testid="evidence-files-check"
          className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
        >
          <h2 className="text-sm font-semibold text-slate-100">{view.check.title}</h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-300">{view.check.text}</p>
          <pre
            data-testid="verify-command"
            className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-200"
          >
            {view.check.command}
          </pre>
          <p className="mt-2 text-xs text-slate-400">{view.check.report_note}</p>
        </section>
        <section
          aria-label={view.holds.title}
          data-testid="evidence-files-holds"
          className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
        >
          <h2 className="text-sm font-semibold text-slate-100">{view.holds.title}</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-slate-300 marker:text-slate-600">
            {view.holds.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      </div>
      <NamesNote>{view.names_note}</NamesNote>
    </section>
  );
}
