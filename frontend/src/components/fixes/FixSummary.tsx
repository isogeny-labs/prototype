import { Fragment, useCallback, useState, type ReactNode } from "react";
import type { FixAction, FixApprovers, FixButton, FixDetail, FixProofRow, OttoProposal } from "../../api";
import { LedgerView } from "../advisories/parts";
import { ProposalCard } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { DemoDataLabel, PrimaryButton, ResultBadge, SecondaryButton, Spinner, StatusChip as ToneChip, formatTime, saveFile } from "../ui";
import { MergeDialog } from "./MergeDialog";
import { DT, Rich, StatusChip } from "./parts";

/** What the user asked for with a button of the summary. The screen makes the call. */
export type FixRequest =
  | { action: "connect" | "run_proof_again" | "merge" | "retest_now" }
  | { action: "open_pull_request"; reviewers: string[] }
  | { action: "approve"; reviewer: string };

function LookButton({
  primary,
  disabled,
  onClick,
  children,
}: {
  primary: boolean;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return primary ? (
    <PrimaryButton disabled={disabled} onClick={onClick}>
      {children}
    </PrimaryButton>
  ) : (
    <SecondaryButton disabled={disabled} onClick={onClick}>
      {children}
    </SecondaryButton>
  );
}

/** What follows a reviewer's name: the Demo data label, and a short note such as "(the person logged in)". */
function ReviewerTags({ demo, note }: { demo: boolean; note: string | null }) {
  return (
    <>
      {demo ? <DemoDataLabel /> : null}
      {note ? <span className="text-xs text-slate-400">{note}</span> : null}
    </>
  );
}

function Proof({ proof }: { proof: FixDetail["proof"] }) {
  const words = (
    <>
      {proof.text}
      {proof.muted ? <span className="text-slate-400"> {proof.muted}</span> : null}
    </>
  );
  if (proof.badge) {
    return (
      <div className="flex flex-wrap items-start gap-2.5">
        <ResultBadge label={proof.badge.label} tone={proof.badge.tone} />
        <p className="min-w-0 flex-1 basis-64 text-slate-300">{words}</p>
      </div>
    );
  }
  if (proof.state === "running") {
    return (
      <div role="status" className="flex items-start gap-2">
        <Spinner className="mt-0.5 h-3.5 w-3.5" />
        <p>{words}</p>
      </div>
    );
  }
  return <p className="text-slate-300">{words}</p>;
}

/** Phase 5c: one of the two proof rows of a library's fix from Otto ("Proven on public copies", "Proven on your
 * system"): the row's own word as a chip, its sentence, its links, and under the first row the research ledger's
 * entries, folded. Every word is the view's; the chip repeats what a trial or a retest showed and decides nothing. */
function ProofRowView({ row }: { row: FixProofRow }) {
  return (
    <>
      <div className="flex flex-wrap items-start gap-2.5">
        <ToneChip label={row.badge.label} tone={row.badge.tone} testId="proof-row-badge" />
        <p data-testid="proof-row-text" className="min-w-0 flex-1 basis-64 break-words text-slate-300">
          {row.text}
        </p>
      </div>
      {row.links.length > 0 ? (
        <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
          {row.links.map((entry, i) => (
            <ItemLinkView key={i} link={entry.link} testId="proof-row-link">
              {entry.label}
            </ItemLinkView>
          ))}
        </p>
      ) : null}
      {row.note ? (
        <p data-testid="proof-row-note" className="mt-1.5 break-words text-xs text-slate-400">
          {row.note}
        </p>
      ) : null}
      {row.ledger ? (
        <div className="mt-2">
          <LedgerView ledger={row.ledger} />
        </div>
      ) : null}
    </>
  );
}

function Approvers({
  approvers,
  ticked,
  busy,
  onTick,
  onApprove,
}: {
  approvers: FixApprovers;
  ticked: ReadonlySet<string>;
  busy: boolean;
  onTick: (reviewer: string) => void;
  onApprove: (reviewer: string) => void;
}) {
  return (
    <>
      {approvers.text ? <p className="text-slate-300">{approvers.text}</p> : null}
      {approvers.options ? (
        <div role="group" aria-labelledby="fix-approvers-label" className="flex flex-wrap gap-x-5 gap-y-2 text-slate-200">
          {approvers.options.map((option) => (
            <label key={option.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={ticked.has(option.id)}
                onChange={() => onTick(option.id)}
                className="h-4 w-4 accent-sky-400"
              />
              <span>{option.name}</span>
              <ReviewerTags demo={option.demo} note={option.note} />
            </label>
          ))}
        </div>
      ) : null}
      {approvers.rows ? (
        <ul>
          {approvers.rows.map((row) => (
            <li
              key={row.id}
              data-testid="approval-row"
              data-reviewer={row.id}
              className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 py-1.5 last:border-b-0"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-100">{row.name}</span>
                <ReviewerTags demo={row.demo} note={row.note} />
              </div>
              {row.approved_at ? (
                <span className="text-slate-300">
                  <span aria-hidden="true" className="font-mono">
                    ✓{" "}
                  </span>
                  {row.approved_text} <time dateTime={row.approved_at}>{formatTime(row.approved_at)}</time>
                </span>
              ) : row.approve_label ? (
                <LookButton primary={row.primary} disabled={busy} onClick={() => onApprove(row.id)}>
                  {row.approve_label}
                </LookButton>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {approvers.footnote ? <p className="mt-1.5 text-xs text-slate-400">{approvers.footnote}</p> : null}
    </>
  );
}

/** A button that could do nothing is drawn switched off: merging needs its confirm box, the patch its file. */
function usable(fix: FixDetail, button: FixButton): boolean {
  if (button.action === "merge") return fix.merge_dialog !== null;
  if (button.action === "download_patch") return fix.patch !== null;
  return true;
}

interface Props {
  fix: FixDetail;
  /** A call is on its way: every button waits for its answer. */
  busy: boolean;
  onRequest: (request: FixRequest) => void;
  /** Phase 5c: the plan a decision on Otto's proposal is recorded in. Without it the proposal is not drawn. */
  planId?: number;
  /** Phase 5c: a decision on Otto's proposal was recorded: the screen reads its view again. */
  onProposalDecided?: (next: OttoProposal) => void;
}

/** One screen about the selected fix: what it does, its proof, who approves, and the button for the next step. Since
 * phase 5c a fix of Otto's is a proposal: its card (Accept, Reject, Undo, Reconsider) sits on top, and a library's
 * fix has two proof rows in place of the one Proof line. */
export function FixSummary({ fix, busy, onRequest, planId, onProposalDecided }: Props) {
  const [picked, setPicked] = useState<ReadonlySet<string> | null>(null);
  const [confirming, setConfirming] = useState(false);
  const closeDialog = useCallback(() => setConfirming(false), []);

  // Until the user touches a box, the ticks are the ones the backend sent.
  const options = fix.approvers.options ?? [];
  const ticked = picked ?? new Set(options.filter((option) => option.checked).map((option) => option.id));

  function tick(reviewer: string) {
    const next = new Set(ticked);
    if (next.has(reviewer)) next.delete(reviewer);
    else next.add(reviewer);
    setPicked(next);
  }

  function press(action: FixAction) {
    if (action === "merge") {
      // Merging asks first. Only the confirm button of the box sends the request.
      setConfirming(true);
    } else if (action === "download_patch") {
      if (fix.patch) saveFile(fix.patch.url, fix.patch.filename);
    } else if (action === "open_pull_request") {
      onRequest({ action, reviewers: options.filter((option) => ticked.has(option.id)).map((option) => option.id) });
    } else {
      onRequest({ action });
    }
  }

  return (
    <section
      data-testid="fix-summary"
      data-fix-id={fix.id}
      aria-label={fix.title}
      className="rounded-xl border border-slate-700 bg-slate-900 p-4"
    >
      <p data-testid="fix-source" className="mt-1 text-sm text-slate-400">
        <Rich parts={fix.source} />
      </p>
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <StatusChip status={fix.status} />
        {fix.labels.map((label) => (
          <span
            key={label}
            className="inline-block whitespace-nowrap rounded border border-slate-500 bg-slate-700/40 px-2 py-0.5 text-xs font-medium text-slate-100"
          >
            {label}
          </span>
        ))}
        {fix.is_demo ? <DemoDataLabel /> : null}
      </div>

      {/* Phase 5c: Otto proposes this fix; a person decides. The card records a decision and runs nothing: the fix's own
          buttons below stay as the view sends them (Connect demo code is off, with the reason, until the accept). */}
      {fix.proposal && planId !== undefined ? (
        <div data-testid="fix-proposal" className="mt-3">
          <ProposalCard planId={planId} proposal={fix.proposal} onDecided={(next) => onProposalDecided?.(next)} />
        </div>
      ) : null}

      {/* "Proof", "Pull request" and "Who approves" only name the rows. Everything that says how the fix stands comes from the view. */}
      <dl className="mt-4 grid gap-x-4 gap-y-3.5 border-t border-slate-800 pt-4 text-sm sm:grid-cols-[120px_1fr]">
        <dt className={DT}>{fix.what.label}</dt>
        <dd data-testid="fix-what" className="space-y-1.5 text-slate-200">
          {fix.what.paragraphs.map((parts, i) => (
            <p key={i}>
              <Rich parts={parts} />
            </p>
          ))}
          {fix.what.server_line ? (
            <p data-testid="server-line" className="text-slate-300">
              {fix.what.server_line}
            </p>
          ) : null}
        </dd>

        {fix.proof_rows && fix.proof_rows.length > 0 ? (
          // Phase 5c: a library's fix from Otto. Two plain rows, each named by the view, in place of the one Proof line.
          fix.proof_rows.map((row) => (
            <Fragment key={row.key}>
              <dt className={DT}>{row.label}</dt>
              <dd data-testid="proof-row" data-key={row.key} data-tone={row.badge.tone} className="min-w-0 text-slate-200">
                <ProofRowView row={row} />
              </dd>
            </Fragment>
          ))
        ) : (
          <>
            <dt className={DT}>Proof</dt>
            <dd data-testid="fix-proof" data-state={fix.proof.state} className="text-slate-200">
              <Proof proof={fix.proof} />
            </dd>
          </>
        )}

        {fix.pull_request ? (
          <>
            <dt className={DT}>Pull request</dt>
            <dd data-testid="fix-pull-request" className="text-slate-200">
              {fix.pull_request.title}{" "}
              <span className="text-slate-300">
                <Rich parts={fix.pull_request.text} />
              </span>
            </dd>
          </>
        ) : null}

        <dt id="fix-approvers-label" className={DT}>
          Who approves
        </dt>
        <dd data-testid="fix-approvers" className="text-slate-200">
          <Approvers
            approvers={fix.approvers}
            ticked={ticked}
            busy={busy}
            onTick={tick}
            onApprove={(reviewer) => onRequest({ action: "approve", reviewer })}
          />
        </dd>
      </dl>

      {fix.actions.buttons.length > 0 || fix.actions.note ? (
        <div data-testid="fix-actions" className="mt-4 border-t border-slate-800 pt-4">
          <div className="flex flex-wrap items-center gap-2.5">
            {fix.actions.buttons.map((button) => (
              <LookButton
                key={button.action}
                primary={button.primary}
                disabled={busy || !button.enabled || !usable(fix, button)}
                onClick={() => press(button.action)}
              >
                {button.label}
              </LookButton>
            ))}
          </div>
          {fix.actions.note ? <p className="mt-2 text-xs text-slate-400">{fix.actions.note}</p> : null}
        </div>
      ) : null}

      {confirming && fix.merge_dialog ? (
        <MergeDialog
          dialog={fix.merge_dialog}
          onCancel={closeDialog}
          onConfirm={() => {
            setConfirming(false);
            onRequest({ action: "merge" });
          }}
        />
      ) : null}
    </section>
  );
}
