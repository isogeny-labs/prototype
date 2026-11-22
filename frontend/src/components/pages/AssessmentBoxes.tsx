import { useState } from "react";
import type { Purpose } from "../../api";
import { Modal } from "../layout";
import { PrimaryButton, SecondaryButton } from "../ui";

/** Phase 5b: the New assessment box (also Rerun as new assessment, filled in for the same file). It closes nothing. */
export function NewAssessmentBox({
  title = "New assessment",
  defaultName,
  defaultPurpose = "full_review",
  defaultReference = "",
  purposes,
  note,
  busy,
  error,
  onStart,
  onCancel,
}: {
  title?: string;
  defaultName: string;
  defaultPurpose?: string;
  defaultReference?: string;
  purposes: Purpose[];
  note?: string;
  busy?: boolean;
  error?: string | null;
  onStart: (box: { name: string; purpose: string; reference: string }) => void;
  onCancel: () => void;
}) {
  // The name follows the suggested one ("Assessment 3", which can arrive a moment after the box opens) until the
  // person types their own. Left empty, the app names it the same way.
  const [typed, setName] = useState<string | null>(null);
  const name = typed ?? defaultName;
  const [purpose, setPurpose] = useState(defaultPurpose);
  const [reference, setReference] = useState(defaultReference);
  return (
    <Modal title={title} onClose={onCancel} testId="new-assessment-box">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onStart({ name, purpose, reference });
        }}
        className="space-y-3 text-sm"
      >
        {note ? <p className="text-slate-400">{note}</p> : null}
        <label className="block">
          <span className="mb-1 block text-slate-300">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-slate-300">Purpose</span>
          <select
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
          >
            {purposes.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-slate-300">Reference (optional)</span>
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            maxLength={200}
            placeholder="For example PCI DSS 12.3.3, or Wave 2"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100 placeholder:text-slate-600"
          />
        </label>
        {error ? (
          <p role="alert" className="text-amber-300">
            {error}
          </p>
        ) : null}
        <div className="flex gap-2 pt-1">
          <PrimaryButton type="submit" disabled={busy} allowWhenClosed>
            Start
          </PrimaryButton>
          <SecondaryButton onClick={onCancel} allowWhenClosed>
            Cancel
          </SecondaryButton>
        </div>
      </form>
    </Modal>
  );
}

/** Phase 5b: Close assessment is a sign-off. It records a name (required) and a note, and can't be undone. */
export function CloseBox({
  oneLoginLine,
  busy,
  error,
  onClose,
  onCancel,
}: {
  oneLoginLine: string;
  busy?: boolean;
  error?: string | null;
  onClose: (box: { signed_off_by: string; note: string }) => void;
  onCancel: () => void;
}) {
  const [by, setBy] = useState("");
  const [note, setNote] = useState("");
  return (
    <Modal title="Close assessment" onClose={onCancel} testId="close-box">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (by.trim()) onClose({ signed_off_by: by.trim(), note });
        }}
        className="space-y-3 text-sm"
      >
        <p className="text-slate-300">Closing freezes this assessment and signs it off. It can&apos;t be reopened.</p>
        <label className="block">
          <span className="mb-1 block text-slate-300">Signed off by</span>
          <input
            value={by}
            onChange={(e) => setBy(e.target.value)}
            maxLength={120}
            required
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-slate-300">Note (optional)</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            rows={2}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
          />
        </label>
        <p className="text-xs text-slate-500">{oneLoginLine}</p>
        {error ? (
          <p role="alert" className="text-amber-300">
            {error}
          </p>
        ) : null}
        <div className="flex gap-2 pt-1">
          <PrimaryButton type="submit" disabled={busy || !by.trim()}>
            Close and sign off
          </PrimaryButton>
          <SecondaryButton onClick={onCancel}>Cancel</SecondaryButton>
        </div>
      </form>
    </Modal>
  );
}
