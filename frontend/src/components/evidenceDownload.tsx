import { api, type EvidenceExport } from "../api";
import { saveFile } from "./ui";

/**
 * Makes the evidence file for a plan and saves both files it answers with (the JSON record and the HTML report).
 * Evidence Lab's and Migration's "Download evidence" buttons both use this, so they download the same thing.
 */
export async function downloadEvidence(planId: number): Promise<EvidenceExport> {
  const made = await api.exportEvidence(planId);
  saveFile(made.json.url, made.json.filename);
  // A short gap, so browsers that drop back-to-back downloads keep both.
  await new Promise((resolve) => setTimeout(resolve, 300));
  saveFile(made.html.url, made.html.filename);
  return made;
}

/** What was downloaded, its fingerprint and how to check it. */
export function DownloadStatus({ exported }: { exported: EvidenceExport }) {
  return (
    <div
      role="status"
      data-testid="download-status"
      className="mt-3 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-xs text-slate-300"
    >
      <p>{exported.message}</p>
      <p className="mt-1">
        <span className="text-slate-500">{exported.fingerprint_label}: </span>
        <span data-testid="evidence-fingerprint" className="break-all font-mono text-slate-200">
          {exported.fingerprint}
        </span>
      </p>
      <p className="mt-1 break-words font-mono text-slate-400">{exported.verify_hint}</p>
    </div>
  );
}
