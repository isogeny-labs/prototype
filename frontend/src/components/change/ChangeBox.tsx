import { useId, useState } from "react";
import { api, errorMessage, type ApprovalsView, type ApplyView, type ChangeButton, type ChangeView } from "../../api";
import { DemoDataLabel, ErrorBox, PrimaryButton, RichTextView, SecondaryButton, WhereFromTag, saveFile } from "../ui";
import { ChangeBadgeView, Section, Steps } from "./ChangeParts";
import { ChangeTry } from "./ChangeTry";

const H4 = "text-[13px] font-semibold text-slate-100";

function Approvals({
  view,
  ticked,
  onTick,
  disabled,
  onAsk,
  onApprove,
}: {
  view: ApprovalsView;
  ticked: ReadonlySet<string>;
  onTick: (id: string) => void;
  disabled: boolean;
  onAsk: () => void;
  onApprove: (reviewer: string) => void;
}) {
  const picker = view.picker;
  const titleId = useId();
  return (
    <div data-testid="change-approvals" className="mt-4">
      <h4 id={titleId} className={H4}>
        {view.title}
      </h4>
      {picker ? (
        <div className="mt-2">
          <div role="group" aria-labelledby={titleId} className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-200">
            {picker.options.map((option) => (
              <label key={option.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={ticked.has(option.id)}
                  onChange={() => onTick(option.id)}
                  className="h-4 w-4 accent-sky-400"
                />
                <span>{option.name}</span>
                {option.demo ? <DemoDataLabel /> : null}
              </label>
            ))}
          </div>
          <div className="mt-2.5">
            <SecondaryButton disabled={disabled || !picker.enabled} onClick={onAsk}>
              {picker.button}
            </SecondaryButton>
          </div>
          {!picker.enabled && picker.reason ? (
            <p data-testid="change-picker-reason" className="mt-1.5 text-xs text-slate-400">
              {picker.reason}
            </p>
          ) : null}
        </div>
      ) : null}
      {view.rows.length > 0 ? (
        <ul className="mt-1.5 text-sm">
          {view.rows.map((row) => (
            <li
              key={row.reviewer}
              data-testid="change-approval-row"
              data-reviewer={row.reviewer}
              className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 py-1.5 last:border-b-0"
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-100">{row.name}</span>
                {row.demo ? <DemoDataLabel /> : null}
              </span>
              {row.approve ? (
                <SecondaryButton disabled={disabled || !row.approve.enabled} onClick={() => onApprove(row.reviewer)}>
                  {row.approve.label}
                </SecondaryButton>
              ) : (
                <span className="text-slate-300">
                  {row.approved_at ? (
                    <span aria-hidden="true" className="font-mono">
                      ✓{" "}
                    </span>
                  ) : null}
                  {row.status_text}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {view.footnote ? <p className="mt-1.5 text-xs text-slate-400">{view.footnote}</p> : null}
    </div>
  );
}

function Applied({ view }: { view: ApplyView }) {
  return (
    <div data-testid="change-applied" className="mt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className={H4}>{view.title}</h4>
        <ChangeBadgeView badge={view.badge} testId="change-applied-badge" />
        {/* 22 November 2026: measured again on the server itself */}
        <WhereFromTag tag={view.source_tag} />
      </div>
      <div className="mt-1.5 space-y-1.5 text-sm text-slate-300">
        {view.paragraphs.map((parts, i) => (
          <p key={i}>
            <RichTextView parts={parts} mono="whitespace-nowrap font-mono text-[0.92em] text-slate-200" />
          </p>
        ))}
      </div>
      {view.differences.length > 0 ? (
        <ul
          data-testid="change-differences"
          className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-200 marker:text-slate-500"
        >
          {view.differences.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      ) : null}
      {view.history.length > 0 ? (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-400">
          {view.history.map((line, i) => (
            <li key={i} data-testid="change-history">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

interface Props {
  change: ChangeView;
  planId: number;
  /** After a call went through: the screen loads its own view again and tells the app. */
  onChanged: () => Promise<void>;
  /** For the "View in Fixes" button inside a result's detail. */
  onViewFix: (fixId: string) => void;
}

/**
 * The change the app built for one system or one fix: what it is, how it was tried, who approved it, how it
 * stands after Apply. Every word, step, verdict and button comes from the view; this draws it and sends the
 * clicks to the server.
 */
export function ChangeBox({ change, planId, onChanged, onViewFix }: Props) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<ReadonlySet<string> | null>(null);
  const titleId = useId();

  const picker = change.approvals?.picker ?? null;
  // Until the user touches a box, the ticks are the ones the view sent.
  const ticked = picked ?? new Set((picker?.options ?? []).filter((o) => o.checked).map((o) => o.id));

  async function run(call: () => Promise<unknown>) {
    setPending(true);
    setError(null);
    try {
      await call();
      await onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPending(false);
    }
  }

  function press(button: ChangeButton) {
    switch (button.action) {
      case "try":
        return void run(() => api.changeTry(planId, change.id));
      case "apply":
        return void run(() => api.changeApply(planId, change.id));
      case "rollback":
        return void run(() => api.changeRollback(planId, change.id));
      case "download":
        // The server names the file; the page only saves it.
        saveFile(api.changeDownloadUrl(planId, change.id), "");
        return;
      default:
        return;
    }
  }

  function tick(id: string) {
    const next = new Set(ticked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  }

  // "approve" and "ask_approval" live in the approvals part; the contract never sends them as buttons.
  const buttons = change.buttons.filter((b) => b.action !== "approve" && b.action !== "ask_approval");
  const reasons = buttons.filter((b) => !b.enabled && b.reason);

  return (
    <section
      data-testid="change-box"
      data-change={change.id}
      data-busy={change.busy ? "true" : "false"}
      aria-labelledby={titleId}
      className="rounded-xl border border-slate-700 bg-slate-900 p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={titleId} className="text-[15px] font-semibold text-slate-50">
          {change.title}
        </h3>
        <ChangeBadgeView badge={change.badge} />
      </div>
      <p className="mt-1.5 text-sm text-slate-300">
        <RichTextView parts={change.intro} mono="whitespace-nowrap font-mono text-[0.92em] text-slate-200" />
      </p>

      <Steps steps={change.steps} />
      {change.sections.map((section, i) => (
        <Section key={i} section={section} />
      ))}
      {change.try ? <ChangeTry view={change.try} onViewFix={onViewFix} /> : null}
      {change.approvals ? (
        <Approvals
          view={change.approvals}
          ticked={ticked}
          onTick={tick}
          disabled={pending}
          onAsk={() =>
            void run(() =>
              api.changeAskApproval(
                planId,
                change.id,
                (picker?.options ?? []).filter((o) => ticked.has(o.id)).map((o) => o.id),
              ),
            )
          }
          onApprove={(reviewer) => void run(() => api.changeApprove(planId, change.id, reviewer))}
        />
      ) : null}
      {change.applied ? <Applied view={change.applied} /> : null}

      {error ? (
        <div className="mt-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      {buttons.length > 0 || change.note ? (
        <div data-testid="change-actions" className="mt-4 border-t border-slate-800 pt-4">
          {buttons.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2.5">
              {buttons.map((button) =>
                button.primary ? (
                  <PrimaryButton
                    key={button.action}
                    disabled={pending || !button.enabled}
                    onClick={() => press(button)}
                  >
                    {button.label}
                  </PrimaryButton>
                ) : (
                  <SecondaryButton
                    key={button.action}
                    disabled={pending || !button.enabled}
                    onClick={() => press(button)}
                  >
                    {button.label}
                  </SecondaryButton>
                ),
              )}
            </div>
          ) : null}
          {reasons.map((button) => (
            <p key={button.action} data-testid="change-reason" className="mt-2 text-xs text-slate-400">
              {button.reason}
            </p>
          ))}
          {change.note ? (
            <p data-testid="change-note" className="mt-2 text-xs text-slate-400">
              {change.note}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
