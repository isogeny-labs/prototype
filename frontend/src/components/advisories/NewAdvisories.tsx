import { useCallback, useState } from "react";
import { api, errorMessage, type AdvisoriesView } from "../../api";
import { Modal } from "../layout";
import { SandboxCopyLabel } from "../otto/ProofBlock";
import { ItemLinkView } from "../related";
import { ErrorBox, PrimaryButton, SecondaryButton, Spinner, StatusChip } from "../ui";

type Lookup = NonNullable<AdvisoriesView["lookup"]>;
type Dialog = Lookup["look"]["dialog"];

/** Phase 6, Otto's research loop: the block "New advisories" on the Advisories page.
 *
 * Two buttons, each behind a box that says what it will do before anything is sent or started:
 * **Look for new advisories** reads one public source about the libraries this assessment names (package names only
 * are sent), and **Design and prove tests** starts the research step for the new advisories that can be tried here.
 * A check is proposed only after its test was proven on public copies; an advisory with no proven test says why.
 * Every word, every state and every reason is the backend's. Looking at this block sends nothing. */
export function NewAdvisories({
  planId,
  lookup,
  onView,
}: {
  planId: number;
  lookup: Lookup;
  onView: (next: AdvisoriesView) => void;
}) {
  const [box, setBox] = useState<"look" | "research" | null>(null);
  const [busy, setBusy] = useState<"look" | "research" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const close = useCallback(() => setBox(null), []);

  async function send(which: "look" | "research") {
    setBusy(which);
    setError(null);
    try {
      onView(await (which === "look" ? api.lookForAdvisories(planId) : api.startResearch(planId)));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
      setBox(null);
    }
  }

  const research = lookup.research;
  const progress = research.progress;
  const dialog: Dialog | null = box === "look" ? lookup.look.dialog : box === "research" ? research.dialog : null;
  return (
    <section
      data-testid="new-advisories"
      aria-label={lookup.title}
      className="mb-5 rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-3xl">
          <h2 className="text-sm font-semibold text-slate-100">{lookup.title}</h2>
          <p className="mt-1 break-words text-slate-300">{lookup.intro}</p>
          <p data-testid="new-advisories-libraries" className="mt-1 break-words text-xs text-slate-400">
            {lookup.libraries_line}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SecondaryButton
            testId="look-for-advisories"
            disabled={!lookup.look.can || busy !== null}
            onClick={() => setBox("look")}
          >
            {busy === "look" ? <Spinner className="h-3.5 w-3.5" /> : null}
            {lookup.look.label}
          </SecondaryButton>
          {research.shown ? (
            <PrimaryButton
              testId="design-and-prove"
              disabled={!research.can || busy !== null}
              onClick={() => setBox("research")}
            >
              {research.label}
            </PrimaryButton>
          ) : null}
        </div>
      </div>
      {!lookup.look.can && lookup.look.blocked_reason ? (
        <p data-testid="look-blocked" className="mt-2 break-words text-xs text-slate-400">
          {lookup.look.blocked_reason}
        </p>
      ) : null}
      {research.shown && !research.can && research.blocked_reason ? (
        <p data-testid="research-blocked" className="mt-2 break-words text-xs text-slate-400">
          {research.blocked_reason}
        </p>
      ) : null}
      {error ? (
        <div className="mt-3" data-testid="new-advisories-error">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      {progress ? (
        <div
          data-testid="research-progress"
          data-running={progress.running}
          className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3"
        >
          <p role="status" className="flex items-start gap-2 break-words text-slate-200">
            {progress.running ? <Spinner className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : null}
            <span data-testid="research-line">{progress.line}</span>
          </p>
          {progress.lines.length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">{progress.title}</summary>
              <ol
                data-testid="research-lines"
                className="mt-2 max-h-56 space-y-0.5 overflow-auto font-mono text-xs text-slate-300"
              >
                {progress.lines.map((line, i) => (
                  <li key={i} className="break-words">
                    {line}
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
        </div>
      ) : null}

      {lookup.last ? (
        <div data-testid="look-result" className="mt-3">
          <p data-testid="look-line" className="break-words text-slate-100">
            {lookup.last.line}
          </p>
          <p data-testid="look-source" className="mt-1 break-words text-xs text-slate-400">
            {lookup.last.source_line}
          </p>
          {lookup.last.notes.map((note) => (
            <p key={note} data-testid="look-note" className="mt-1 break-words text-xs text-slate-400">
              {note}
            </p>
          ))}
          {lookup.last.rows.length === 0 ? (
            <p data-testid="look-empty" className="mt-2 text-slate-300">
              {lookup.last.empty}
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {lookup.last.rows.map((row) => (
                <li
                  key={row.id}
                  data-testid="found-advisory"
                  data-advisory={row.id}
                  data-state={row.state.key}
                  className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/40 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-slate-300">{row.id}</span>
                    <StatusChip label={row.state.label} tone={row.state.tone} size="sm" wrap testId="found-state" />
                    {row.sandbox ? <SandboxCopyLabel testId="found-sandbox" /> : null}
                    <span className="text-xs text-slate-500">
                      {row.library} · published {row.published}
                    </span>
                  </div>
                  <p data-testid="found-title" className="mt-1.5 break-words text-slate-100">
                    {row.title}
                  </p>
                  <p data-testid="found-fits" className="mt-1 break-words text-[13px] text-slate-300">
                    {row.fits}
                  </p>
                  {row.reason ? (
                    <p data-testid="found-reason" className="mt-1 break-words text-[13px] text-slate-300">
                      {row.reason}
                    </p>
                  ) : null}
                  <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                    {row.link ? (
                      <ItemLinkView link={row.link} testId="found-link">
                        Open it in the list below
                      </ItemLinkView>
                    ) : null}
                    {row.watch ? (
                      <ItemLinkView link={row.watch.link} testId="found-watch-link">
                        {row.watch.label}
                      </ItemLinkView>
                    ) : null}
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-testid="found-source"
                      className="text-sky-300 underline-offset-2 hover:underline"
                    >
                      {row.publisher} ↗
                    </a>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {lookup.sandbox_line ? (
        <p data-testid="new-advisories-sandbox" className="mt-3 break-words text-[13px] text-slate-300">
          {lookup.sandbox_line}
        </p>
      ) : null}
      <p
        data-testid="new-advisories-covers"
        className="mt-3 break-words border-t border-slate-800 pt-3 text-xs text-slate-500"
      >
        {lookup.covers}
      </p>

      {dialog && box ? (
        <Modal title={dialog.title} onClose={close} testId={box === "look" ? "look-dialog" : "research-dialog"}>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-300 marker:text-slate-500">
            {dialog.lines.map((line) => (
              <li key={line} className="break-words">
                {line}
              </li>
            ))}
          </ul>
          {/* Cancel comes first, so the keyboard starts on it: pressing Enter straight away sends nothing. */}
          <div className="mt-4 flex flex-wrap justify-end gap-2.5">
            <SecondaryButton testId="lookup-cancel" disabled={busy !== null} onClick={close}>
              {dialog.cancel}
            </SecondaryButton>
            <PrimaryButton testId="lookup-confirm" busy={busy !== null} onClick={() => void send(box)}>
              {busy !== null ? <Spinner className="h-3.5 w-3.5" /> : null}
              {dialog.confirm}
            </PrimaryButton>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
