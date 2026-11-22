import { useState } from "react";
import { api, errorMessage, type OttoProposal } from "../../api";
import { LedgerView } from "../advisories/parts";
import { Modal } from "../layout";
import { ItemLinkView } from "../related";
import { ErrorBox, PrimaryButton, SecondaryButton, Spinner, StatusChip } from "../ui";
import { ProofBlock } from "./ProofBlock";

type Decision = OttoProposal["buttons"][number]["key"];

/** The small tag on everything Otto produces. */
export function FromOttoTag({ label = "From Otto", testId = "from-otto" }: { label?: string; testId?: string }) {
  return (
    <span
      data-testid={testId}
      className="inline-block whitespace-nowrap rounded border border-slate-500 bg-slate-700/40 px-2 py-0.5 text-xs font-medium text-slate-100"
    >
      {label}
    </span>
  );
}

/** Where one of Otto's proposals stands, as a chip: "Proposed", "Added", "Accepted" or "Not added (reason)". The reason
 * is a person's own words, so it may hold one long unbroken run (an address, a ticket path): the chip never grows wider
 * than the room it has, and such a run is broken at its edge. Ordinary words stay whole. */
export function ProposalStatusChip({ status, testId }: { status: Pick<OttoProposal["status"], "word" | "tone">; testId?: string }) {
  return (
    <span className="inline-block min-w-0 max-w-full break-words align-middle [&>span>span:last-child]:min-w-0 [&>span]:max-w-full">
      <StatusChip label={status.word} tone={status.tone} size="sm" wrap testId={testId} />
    </span>
  );
}

/** Phase 5c: one of Otto's proposals, wherever it shows (Advisories, Fixes, Migration, Dependencies). Otto proposes;
 * a person decides: Accept, Reject (with an optional short reason), Undo of an accept, Reconsider of a reject. Every
 * word, state and reason here is the backend's. A decision runs nothing; the answer is the proposal as it now stands,
 * and the page then reads its own view again (`onDecided`). A button the backend would refuse is off and says why. */
export function ProposalCard({
  planId,
  proposal,
  onDecided,
  showTitle = true,
  showWhere = false,
}: {
  planId: number;
  proposal: OttoProposal;
  /** Called after a decision was recorded, with the proposal as it now stands. */
  onDecided: (next: OttoProposal) => void;
  /** Off where the proposal sits under a heading that already names it. */
  showTitle?: boolean;
  /** On a list of every proposal: the way to the page it lives on. */
  showWhere?: boolean;
}) {
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  async function decide(decision: Decision, why?: string) {
    setBusy(decision);
    setError(null);
    try {
      const next = await api.decideProposal(planId, proposal.id, decision, why);
      setRejecting(false);
      setReason("");
      onDecided(next);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  const dialog = proposal.reject_dialog;
  const blocked = proposal.buttons.filter((b) => !b.can && b.blocked_reason);

  return (
    <div
      data-testid="otto-proposal"
      data-proposal={proposal.id}
      data-kind={proposal.kind}
      data-state={proposal.status.key}
      className="min-w-0 rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <FromOttoTag label={proposal.label} testId="proposal-label" />
        <ProposalStatusChip status={proposal.status} testId="proposal-status" />
      </div>
      {showTitle ? (
        <p data-testid="proposal-title" className="mt-2 break-words font-medium text-slate-100">
          {proposal.title}
        </p>
      ) : null}
      <p data-testid="proposal-why" className="mt-1.5 break-words text-slate-200">
        <span className="text-xs text-slate-500">{proposal.why_label}: </span>
        {proposal.why}
      </p>
      {proposal.lines.length > 0 ? (
        <ul data-testid="proposal-lines" className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-slate-300 marker:text-slate-500">
          {proposal.lines.map((line, i) => (
            <li key={i} className="break-words">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
      {/* Sandbox research (a prototype): how the proposed test was proven, folded. It only shows; it decides nothing. */}
      {proposal.proof ? <ProofBlock proof={proposal.proof} /> : null}
      {proposal.decided_line ? (
        <p data-testid="proposal-decided" className="mt-2 break-words text-[13px] text-slate-300">
          {proposal.decided_line}
        </p>
      ) : null}
      {proposal.effect ? (
        <p data-testid="proposal-effect" className="mt-1 break-words text-[13px] text-slate-200">
          {proposal.effect}
        </p>
      ) : null}

      {proposal.buttons.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {proposal.buttons.map((b) =>
            b.key === "accept" ? (
              <PrimaryButton key={b.key} testId="proposal-accept" disabled={!b.can || busy !== null} busy={busy === "accept"} onClick={() => void decide("accept")}>
                {busy === "accept" ? <Spinner className="h-3.5 w-3.5" /> : null}
                {b.label}
              </PrimaryButton>
            ) : (
              <SecondaryButton
                key={b.key}
                testId={`proposal-${b.key}`}
                disabled={!b.can || busy !== null}
                onClick={() => (b.key === "reject" ? setRejecting(true) : void decide(b.key))}
              >
                {busy === b.key ? <Spinner className="h-3.5 w-3.5" /> : null}
                {b.label}
              </SecondaryButton>
            ),
          )}
        </div>
      ) : null}
      {blocked.length > 0 ? (
        <p data-testid="proposal-blocked" className="mt-2 break-words text-[13px] text-slate-300">
          {Array.from(new Set(blocked.map((b) => b.blocked_reason))).join(" ")}
        </p>
      ) : null}
      {proposal.note ? (
        <p data-testid="proposal-note" className="mt-2 break-words text-xs text-slate-400">
          {proposal.note}
        </p>
      ) : null}
      {error ? (
        <div className="mt-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      {showWhere ? (
        <p className="mt-2 text-xs">
          <ItemLinkView link={proposal.link} testId="proposal-where">
            Open where it lives
          </ItemLinkView>
        </p>
      ) : null}

      {proposal.history.count > 0 ? (
        <details data-testid="proposal-history" className="mt-3 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-slate-300 hover:text-slate-100">
            {proposal.history.title} <span className="tabular-nums text-slate-500">({proposal.history.count})</span>
          </summary>
          <ol className="mt-2 space-y-1 text-xs text-slate-300">
            {proposal.history.rows.map((row) => (
              <li key={row.number} data-testid="proposal-decision" className="break-words">
                {row.line}
              </li>
            ))}
          </ol>
          <p className="mt-2 break-words text-xs text-slate-400">{proposal.history.footnote}</p>
          {proposal.history.ledger ? (
            <div className="mt-2">
              <LedgerView ledger={proposal.history.ledger} />
            </div>
          ) : null}
        </details>
      ) : null}

      {rejecting && dialog ? (
        <Modal title={dialog.title} onClose={() => setRejecting(false)} testId="proposal-reject-dialog">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void decide("reject", reason.trim() || undefined);
            }}
          >
            <p className="break-words text-sm text-slate-300">{dialog.line}</p>
            <label className="mt-3 block text-sm text-slate-200">
              <span className="block text-xs text-slate-400">{dialog.reason_label}</span>
              <input
                type="text"
                value={reason}
                maxLength={dialog.max}
                onChange={(e) => setReason(e.target.value)}
                data-testid="proposal-reject-reason"
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
              />
            </label>
            {error ? (
              <div className="mt-3">
                <ErrorBox>{error}</ErrorBox>
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <SecondaryButton testId="proposal-reject-cancel" onClick={() => setRejecting(false)}>
                {dialog.cancel}
              </SecondaryButton>
              <PrimaryButton type="submit" testId="proposal-reject-confirm" busy={busy === "reject"}>
                {busy === "reject" ? <Spinner className="h-3.5 w-3.5" /> : null}
                {dialog.confirm}
              </PrimaryButton>
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
