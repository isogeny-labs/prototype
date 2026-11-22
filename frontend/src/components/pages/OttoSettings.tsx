import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, errorMessage, type OttoPackCard, type OttoSettingsView, type OttoUpdate } from "../../api";
import { Modal } from "../layout";
import { ErrorBox, PrimaryButton, SecondaryButton, Spinner } from "../ui";
import { Section } from "./parts";

const CARD = "space-y-4 rounded-xl border border-slate-800 bg-slate-900/30 p-4 text-sm text-slate-300";
const SMALL = "text-xs text-slate-400";

/** Which call is on its way (every button of the two sections waits for its answer). */
type Busy = "check" | "install" | "switch" | "limit" | "name";
/** The section an error belongs to, so it is shown once, where it happened. */
type Where = "packs" | "live" | "name";

/** One installed test pack: the view's line about it, who signed it, and its fingerprint cut short (the whole value
 * shows on hover). A pack made on this computer says so in its own line. */
function PackCard({ pack }: { pack: OttoPackCard }) {
  return (
    <li
      data-testid="otto-pack-card"
      data-version={pack.version}
      data-made-here={pack.made_here || undefined}
      className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/60 p-3"
    >
      <p className="break-words text-slate-100">{pack.line}</p>
      <dl className="mt-1.5 grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-2 gap-y-0.5 text-xs">
        <dt className="text-slate-500">Signed by</dt>
        <dd className="min-w-0 break-words text-slate-300">{pack.signer}</dd>
        <dt className="text-slate-500">Fingerprint</dt>
        <dd className="min-w-0">
          <span data-testid="otto-pack-fingerprint" title={pack.fingerprint} className="font-mono text-slate-300">
            {pack.fingerprint.slice(0, 12)}
          </span>
        </dd>
      </dl>
    </li>
  );
}

/** Phase 5c: the two Otto sections of Settings. Test packs: what is installed, Check for updates (it looks in a folder
 * on this computer), and Install update behind a box that only its Install button confirms. Live Otto: whether Otto may
 * ask Claude through the key on this computer, and the spending limit per run. The key itself is never shown, asked
 * for or typed. Every word is the backend's; each call answers with the whole view as it now stands. */
export function OttoSettings({ section }: { section: string | null }) {
  const [view, setView] = useState<OttoSettingsView | null>(null);
  const [error, setError] = useState<{ where: Where; text: string } | null>(null);
  const [busy, setBusy] = useState<Busy | null>(null);
  const [confirming, setConfirming] = useState(false);
  // The amount as typed; until the person types, the field shows the saved limit.
  const [typedLimit, setTypedLimit] = useState<string | null>(null);
  const [limitSaved, setLimitSaved] = useState(false);
  // Phase 6a: the name as typed; until the person types, the field shows the saved one.
  const [typedName, setTypedName] = useState<string | null>(null);
  const [nameSaved, setNameSaved] = useState(false);
  const closeDialog = useCallback(() => setConfirming(false), []);

  useEffect(() => {
    let live = true;
    api
      .getOtto()
      .then((next) => {
        if (live) setView(next);
      })
      .catch((e: unknown) => {
        if (live) setError({ where: "packs", text: errorMessage(e) });
      });
    return () => {
      live = false;
    };
  }, []);

  // A link to Settings can name the Test packs section (the Advisories page does): bring it into view, and again once
  // its content is drawn.
  const loaded = view !== null;
  useEffect(() => {
    // (phase 6a: the Otto panel's status line links to the Live Otto section the same way)
    if (section !== "test-packs" && section !== "live-otto" && section !== "your-name") return;
    // jsdom has no scrollIntoView; a browser always does.
    document.getElementById(section)?.scrollIntoView?.({ block: "start" });
  }, [section, loaded]);

  /** Makes one call and shows the view it answers with, or its refusal in the section it belongs to. `settled` runs in
   * the same moment as the answer is shown (the install box closes with it). */
  async function run(what: Busy, where: Where, call: () => Promise<OttoSettingsView>, settled?: () => void): Promise<boolean> {
    setBusy(what);
    setError(null);
    setLimitSaved(false);
    try {
      const next = await call();
      settled?.();
      // A Live Otto call answers without looking in the updates folder again, so what Check for updates found (and
      // everything else about the packs) stays on screen as it was.
      setView((before) => (where === "live" && before ? { ...next, packs: before.packs } : next));
      return true;
    } catch (e) {
      settled?.();
      setError({ where, text: errorMessage(e) });
      return false;
    } finally {
      setBusy(null);
    }
  }

  // Installed or refused, the box closes: a refusal is shown in the section.
  const install = (update: OttoUpdate) => void run("install", "packs", () => api.installPack(update.version), closeDialog);

  async function saveLimit(e: FormEvent, saved: string) {
    e.preventDefault();
    if (busy !== null) return;
    const ok = await run("limit", "live", () => api.setLiveOtto({ limit: typedLimit ?? saved }));
    if (ok) {
      // The field goes back to showing the limit as the backend now words it.
      setTypedLimit(null);
      setLimitSaved(true);
    }
  }

  async function saveName(e: FormEvent, saved: string) {
    e.preventDefault();
    if (busy !== null) return;
    const ok = await run("name", "name", () => api.setDecisionName(typedName ?? saved));
    if (ok) {
      setTypedName(null);
      setNameSaved(true);
    }
  }

  const errorBox = (where: Where) =>
    error?.where === where ? (
      <div data-testid="otto-error">
        <ErrorBox>{error.text}</ErrorBox>
      </div>
    ) : null;

  if (!view) {
    return (
      <Section title="Test packs" id="test-packs" testId="test-packs">
        {error ? (
          errorBox("packs")
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </Section>
    );
  }

  const { packs, live } = view;
  const update = packs.update;
  const switchOff = !live.switch.on && !live.switch.can_turn_on;

  return (
    <>
      <Section title={packs.title} id="test-packs" testId="test-packs">
        <div className={CARD}>
          <p>{packs.intro}</p>

          <div>
            <p data-testid="otto-installed-line" className="font-medium text-slate-100">
              {packs.installed_line}
            </p>
            {packs.unreadable_line ? (
              <p data-testid="otto-unreadable-line" className="mt-1 break-words text-amber-200">
                {packs.unreadable_line}
              </p>
            ) : null}
            {packs.counts_line ? (
              <p data-testid="otto-counts-line" className={`mt-0.5 ${SMALL}`}>
                {packs.counts_line}
              </p>
            ) : null}
          </div>

          {packs.installed.length > 0 ? (
            <ul className="grid gap-2 sm:grid-cols-2">
              {packs.installed.map((pack) => (
                <PackCard key={pack.fingerprint} pack={pack} />
              ))}
            </ul>
          ) : null}

          <div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <SecondaryButton testId="otto-check-updates" disabled={busy !== null} onClick={() => void run("check", "packs", () => api.checkPackUpdates())}>
                {busy === "check" ? <Spinner className="h-3.5 w-3.5" /> : null}
                {packs.check.button}
              </SecondaryButton>
              <span className={SMALL}>{packs.check.note}</span>
            </div>
            {packs.checked_line ? (
              <p role="status" data-testid="otto-checked-line" className="mt-2.5 text-slate-200">
                {packs.checked_line}
              </p>
            ) : null}
          </div>

          {/* A file in the updates folder that was not taken, with the backend's one plain reason: a calm warning. */}
          {packs.refused.length > 0 ? (
            <ul data-testid="otto-refused" className="space-y-2 rounded-lg border border-dashed border-slate-500 bg-slate-900 p-3">
              {packs.refused.map((r, i) => (
                <li key={`${r.file}-${i}`} data-testid="otto-refused-item" className="min-w-0 text-[13px]">
                  <span className="block break-words font-mono text-slate-100">{r.file}</span>
                  <span className="block break-words text-slate-300">{r.reason}</span>
                </li>
              ))}
            </ul>
          ) : null}

          {update ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-400/35 bg-sky-400/5 p-3">
              <p data-testid="otto-update-line" className="min-w-0 break-words text-slate-200">
                {update.line}
              </p>
              <PrimaryButton testId="otto-install-update" disabled={busy !== null} onClick={() => setConfirming(true)}>
                {update.button}
              </PrimaryButton>
            </div>
          ) : null}

          <p data-testid="otto-order-note" className={SMALL}>
            {packs.order_note}
          </p>

          {errorBox("packs")}
        </div>

        {/* The two status lines: Otto's harness on this computer, and where Otto's answers come from. */}
        <ul className="mt-3 space-y-1.5 text-xs text-slate-400">
          {/* Otto not on this computer: a calm note in the backend's words, not an error. */}
          <li
            data-testid="otto-harness-line"
            data-installed={view.harness.installed}
            className={view.harness.installed ? "break-words px-1" : "break-words rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-slate-200"}
          >
            {view.harness.line}
          </li>
          <li data-testid="otto-answers-line" data-live={view.answers.live} className="break-words px-1">
            {view.answers.line}
          </li>
        </ul>

        {confirming && update ? (
          <Modal title={update.dialog.title} onClose={closeDialog} testId="otto-install-dialog">
            <div className="space-y-2 text-sm text-slate-300">
              {update.dialog.lines.map((line, i) => (
                <p key={i} className="break-words">
                  {line}
                </p>
              ))}
            </div>
            {/* Cancel comes first, so the keyboard starts on it: pressing Enter straight away installs nothing. */}
            <div className="mt-4 flex flex-wrap justify-end gap-2.5">
              <SecondaryButton testId="otto-install-cancel" disabled={busy === "install"} onClick={closeDialog}>
                {update.dialog.cancel}
              </SecondaryButton>
              <PrimaryButton testId="otto-install-confirm" busy={busy === "install"} onClick={() => install(update)}>
                {busy === "install" ? <Spinner className="h-3.5 w-3.5" /> : null}
                {update.dialog.confirm}
              </PrimaryButton>
            </div>
          </Modal>
        ) : null}
      </Section>

      {view.name ? (
        <Section title={view.name.title} id="your-name" testId="your-name">
          <div className={CARD}>
            <form onSubmit={(e) => void saveName(e, view.name?.value ?? "")}>
              <label htmlFor="otto-your-name" className="block text-xs text-slate-400">
                {view.name.label}
              </label>
              <div className="mt-1 flex flex-wrap items-center gap-3">
                <input
                  id="otto-your-name"
                  data-testid="otto-your-name"
                  autoComplete="name"
                  value={typedName ?? view.name.value}
                  onChange={(e) => {
                    setTypedName(e.target.value);
                    setNameSaved(false);
                  }}
                  maxLength={view.name.max}
                  className="w-72 max-w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100"
                />
                <PrimaryButton type="submit" testId="otto-your-name-save" disabled={busy !== null && busy !== "name"} busy={busy === "name"}>
                  {view.name.save}
                </PrimaryButton>
                {nameSaved ? (
                  <p role="status" className={SMALL}>
                    Saved.
                  </p>
                ) : null}
              </div>
            </form>
            <p data-testid="otto-your-name-line" className="break-words text-slate-200">
              {view.name.line}
            </p>
            <p className={`break-words ${SMALL}`}>{view.name.note}</p>
            {errorBox("name")}
          </div>
        </Section>
      ) : null}

      <Section title={live.title} id="live-otto" testId="live-otto">
        <div className={CARD}>
          <p data-testid="live-otto-key-line" className="break-words">
            {live.key_line}
          </p>

          <div className="flex items-start justify-between gap-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <div className="min-w-0">
              <label htmlFor="live-otto-switch" className="block text-sm font-medium text-slate-100">
                {live.switch.label}
              </label>
              {live.switch.blocked_reason ? (
                <p id="live-otto-switch-reason" data-testid="live-otto-switch-reason" className={`mt-1 break-words ${SMALL}`}>
                  {live.switch.blocked_reason}
                </p>
              ) : null}
            </div>
            <input
              id="live-otto-switch"
              type="checkbox"
              role="switch"
              data-testid="live-otto-switch"
              aria-checked={live.switch.on}
              aria-describedby={live.switch.blocked_reason ? "live-otto-switch-reason" : undefined}
              checked={live.switch.on}
              disabled={switchOff || busy !== null}
              onChange={(e) => {
                // A switch that is off and can't be turned on changes nothing, however the event got here.
                if (switchOff || busy !== null) return;
                const on = e.target.checked;
                void run("switch", "live", () => api.setLiveOtto({ on }));
              }}
              className="mt-0.5 h-4 w-4 shrink-0 accent-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>

          <div>
            <form onSubmit={(e) => void saveLimit(e, live.limit.value)}>
              <label htmlFor="live-otto-limit" className="block text-xs text-slate-400">
                {live.limit.label}
              </label>
              <div className="mt-1 flex flex-wrap items-center gap-3">
                <input
                  id="live-otto-limit"
                  data-testid="live-otto-limit"
                  inputMode="decimal"
                  autoComplete="off"
                  value={typedLimit ?? live.limit.value}
                  onChange={(e) => {
                    setTypedLimit(e.target.value);
                    setLimitSaved(false);
                  }}
                  maxLength={12}
                  className="w-40 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100"
                />
                <PrimaryButton type="submit" testId="live-otto-save" disabled={busy !== null && busy !== "limit"} busy={busy === "limit"}>
                  {live.limit.save}
                </PrimaryButton>
                {limitSaved ? (
                  <p role="status" className={SMALL}>
                    Saved.
                  </p>
                ) : null}
              </div>
            </form>
            <p className={`mt-2 break-words ${SMALL}`}>{live.limit.note}</p>
          </div>

          {errorBox("live")}

          <p data-testid="live-otto-sent-line" className="break-words">
            {live.sent_line}
          </p>
          <p data-testid="live-otto-status-line" className="break-words text-slate-200">
            {live.status_line}
          </p>
          <p data-testid="live-otto-price-line" className={`break-words ${SMALL}`}>
            {live.price_line}
          </p>
        </div>
      </Section>
    </>
  );
}
