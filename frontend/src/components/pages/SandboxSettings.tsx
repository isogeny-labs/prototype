import { useCallback, useState, type FormEvent } from "react";
import { api, type OttoSandboxSection, type OttoSettingsView } from "../../api";
import { Modal } from "../layout";
import { PrimaryButton, SecondaryButton } from "../ui";
import { Section } from "./parts";

const CARD = "space-y-4 rounded-xl border border-slate-800 bg-slate-900/30 p-4 text-sm text-slate-300";
const SMALL = "text-xs text-slate-400";
const ROW = "flex items-start justify-between gap-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3";

type Limit = "run" | "day";

/** Sandbox research (a prototype for Isogeny's own sandbox): the one switch everything new sits behind, its second tick
 * and its two spending limits. The switch is off by default and greyed, with every plain reason, where it can't be on.
 * Turning it ON first opens a box that says what will happen while it is on; nothing is sent before the click in that
 * box. Turning it off needs no box. Every word is the backend's; each call answers with the whole Settings view. */
export function SandboxSettings({
  sandbox,
  busy,
  call,
  error,
}: {
  sandbox: OttoSandboxSection;
  /** Another call of the Settings page is on its way: every control here waits for it. */
  busy: boolean;
  /** Makes one call and shows the view it answers with; false when it was refused (the refusal is shown here). */
  call: (make: () => Promise<OttoSettingsView>) => Promise<boolean>;
  error: React.ReactNode;
}) {
  const [asking, setAsking] = useState(false);
  const [typed, setTyped] = useState<{ run: string | null; day: string | null }>({ run: null, day: null });
  const [saved, setSaved] = useState<Limit | null>(null);
  const closeBox = useCallback(() => setAsking(false), []);
  const { switch: sw, by_itself: tick } = sandbox;
  const switchOff = !sw.on && !sw.can_turn_on;
  const tickOff = !tick.on && !tick.can_turn_on;

  async function saveLimit(e: FormEvent, which: Limit, shown: string) {
    e.preventDefault();
    if (busy) return;
    setSaved(null);
    const amount = typed[which] ?? shown;
    const ok = await call(() => api.setSandbox(which === "run" ? { run_limit: amount } : { day_limit: amount }));
    if (ok) {
      setTyped((before) => ({ ...before, [which]: null }));
      setSaved(which);
    }
  }

  const limitField = (which: Limit, limit: OttoSandboxSection["run_limit"]) => (
    <form onSubmit={(e) => void saveLimit(e, which, limit.value)} className="min-w-0 flex-1">
      <label htmlFor={`sandbox-${which}-limit`} className="block text-xs text-slate-400">
        {limit.label}
      </label>
      <div className="mt-1 flex items-center gap-2">
        <input
          id={`sandbox-${which}-limit`}
          data-testid={`sandbox-${which}-limit`}
          inputMode="decimal"
          maxLength={12}
          value={typed[which] ?? limit.value}
          onChange={(e) => {
            setSaved(null);
            setTyped((before) => ({ ...before, [which]: e.target.value }));
          }}
          className="w-28 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        />
        <PrimaryButton type="submit" testId={`sandbox-${which}-save`} disabled={busy}>
          {limit.save}
        </PrimaryButton>
        {saved === which ? (
          <span role="status" data-testid={`sandbox-${which}-saved`} className={SMALL}>
            Saved.
          </span>
        ) : null}
      </div>
    </form>
  );

  return (
    <Section title={sandbox.title} id="sandbox-research" testId="sandbox-research">
      <div className={CARD}>
        <p data-testid="sandbox-intro" className="break-words">
          {sandbox.intro}
        </p>

        <div className={ROW}>
          <div className="min-w-0">
            <label htmlFor="sandbox-switch" className="block text-sm font-medium text-slate-100">
              {sw.label}
            </label>
            {sw.blocked_reasons.length > 0 ? (
              <ul
                id="sandbox-switch-reasons"
                data-testid="sandbox-switch-reasons"
                className={`mt-1 space-y-1 ${SMALL}`}
              >
                {sw.blocked_reasons.map((reason) => (
                  <li key={reason} className="break-words">
                    {reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <input
            id="sandbox-switch"
            type="checkbox"
            role="switch"
            data-testid="sandbox-switch"
            aria-checked={sw.on}
            aria-describedby={sw.blocked_reasons.length > 0 ? "sandbox-switch-reasons" : undefined}
            checked={sw.on}
            disabled={switchOff || busy}
            onChange={(e) => {
              // A switch that is off and can't be turned on changes nothing, however the event got here.
              if (switchOff || busy) return;
              if (e.target.checked)
                setAsking(true); // turning it on: the box first; nothing is sent yet
              else void call(() => api.setSandbox({ on: false }));
            }}
            className="mt-0.5 h-5 w-5 shrink-0 accent-indigo-500 disabled:opacity-50"
          />
        </div>

        <div className={ROW}>
          <div className="min-w-0">
            <label htmlFor="sandbox-by-itself" className="block text-sm font-medium text-slate-100">
              {tick.label}
            </label>
            <p data-testid="sandbox-by-itself-line" className={`mt-1 break-words ${SMALL}`}>
              {tick.line}
            </p>
            {tick.blocked_reason ? (
              <p
                id="sandbox-by-itself-reason"
                data-testid="sandbox-by-itself-reason"
                className={`mt-1 break-words ${SMALL}`}
              >
                {tick.blocked_reason}
              </p>
            ) : null}
          </div>
          <input
            id="sandbox-by-itself"
            type="checkbox"
            data-testid="sandbox-by-itself"
            aria-describedby={tick.blocked_reason ? "sandbox-by-itself-reason" : undefined}
            checked={tick.on}
            disabled={tickOff || busy}
            onChange={(e) => {
              if (tickOff || busy) return;
              const on = e.target.checked;
              void call(() => api.setSandbox({ by_itself: on }));
            }}
            className="mt-0.5 h-5 w-5 shrink-0 accent-indigo-500 disabled:opacity-50"
          />
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex flex-wrap gap-6">
            {limitField("run", sandbox.run_limit)}
            {limitField("day", sandbox.day_limit)}
          </div>
          <p data-testid="sandbox-limits-note" className={`mt-2 break-words ${SMALL}`}>
            {sandbox.limits_note}
          </p>
        </div>

        {error}

        <p data-testid="sandbox-status-line" className="break-words text-slate-200">
          {sandbox.status_line}
        </p>
        {sandbox.spent_line ? (
          <p data-testid="sandbox-spent-line" className={`break-words ${SMALL}`}>
            {sandbox.spent_line}
          </p>
        ) : null}
      </div>

      {asking ? (
        <Modal title={sandbox.box.title} onClose={closeBox} testId="sandbox-box">
          <ul className="list-disc space-y-2 pl-5 text-sm text-slate-300">
            {sandbox.box.lines.map((line) => (
              <li key={line} className="break-words">
                {line}
              </li>
            ))}
          </ul>
          <div className="mt-5 flex justify-end gap-2">
            <SecondaryButton testId="sandbox-box-cancel" disabled={busy} onClick={closeBox}>
              {sandbox.box.cancel}
            </SecondaryButton>
            <PrimaryButton
              testId="sandbox-box-confirm"
              disabled={busy}
              onClick={() => {
                // The one click that turns it on. Turned on or refused, the box closes: a refusal is shown in the section.
                void call(() => api.setSandbox({ on: true })).finally(closeBox);
              }}
            >
              {sandbox.box.confirm}
            </PrimaryButton>
          </div>
        </Modal>
      ) : null}
    </Section>
  );
}
