import type { ChangeResult, ChangeResultSide, ChangeRow, ChangeTest } from "../../api";
import { CodeLines } from "../fixes/ChangeBody";
import { DetailPanel } from "../layout";
import { ItemLinkView } from "../related";
import { DemoDataLabel, PrimaryButton, ProgressBar, ResultBadge, Spinner, StatusChip, WhereFromTag } from "../ui";

const H = "mb-1.5 text-[13px] font-semibold text-slate-100";

/** The tests of one list (picked, or not picked), each with the rule that placed it, in one sentence. */
function Tests({ tests, testId }: { tests: ChangeTest[]; testId: string }) {
  return (
    <ul data-testid={testId} className="space-y-1.5">
      {tests.map((t) => (
        <li key={t.item_id} data-testid="change-test" className="min-w-0 break-words text-sm">
          <ItemLinkView link={t.link} className="font-medium text-sky-300 underline-offset-2 hover:underline">
            {t.title}
          </ItemLinkView>
          <span className="block text-xs text-slate-400">{t.reason}</span>
        </li>
      ))}
    </ul>
  );
}

/** One side of before and now: the reviewer's own word for that run and its plain sentence, with where its evidence is. */
function Side({ heading, side, note, testId }: { heading: string; side: ChangeResultSide | null; note?: string | null; testId: string }) {
  return (
    <div data-testid={testId} className="min-w-0">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        {heading}
        {side?.ran_on ? <span className="normal-case tracking-normal text-slate-400">: {side.ran_on}</span> : null}
      </p>
      {side ? (
        <>
          <span className="flex flex-wrap items-center gap-1.5">
            <ResultBadge label={side.label} tone={side.tone} wrap />
            <WhereFromTag tag={side.source_tag} />
          </span>
          <p className="mt-1.5 break-words text-[13px] leading-snug text-slate-300">{side.plain}</p>
          {side.source_tag?.note ? <p data-testid="source-note" className="mt-1 break-words text-xs text-slate-400">{side.source_tag.note}</p> : null}
          {side.link ? (
            <p className="mt-1 text-xs">
              <ItemLinkView link={side.link} testId="change-result-link" className="text-sky-300 underline-offset-2 hover:underline">
                See the evidence
              </ItemLinkView>
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-[13px] text-slate-400">No reviewed run yet.</p>
      )}
      {note ? <p className="mt-1 break-words text-xs text-slate-400">{note}</p> : null}
    </div>
  );
}

function Result({ result }: { result: ChangeResult }) {
  return (
    <li data-testid="change-result" data-outcome={result.outcome ?? undefined} className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 break-words text-sm font-medium text-slate-100">{result.title}</p>
        {result.differs ? (
          <span data-testid="change-result-differs" className="text-xs text-slate-300">
            {result.differs}
          </span>
        ) : null}
      </div>
      {result.job ? (
        // The run's own progress, in the runner's words, while it waits or runs.
        <div data-testid="change-result-job" data-status={result.job.status} className="mt-2 flex items-start gap-2 text-[13px] text-slate-300">
          {result.job.status === "running" ? <Spinner className="mt-0.5 h-3.5 w-3.5" /> : null}
          <div className="min-w-0">
            <p>{result.job.status === "waiting" ? "Waiting for its turn" : "Running"}</p>
            {result.job.progress_text ? <p className="text-xs text-slate-400">{result.job.progress_text}</p> : null}
            {result.job.progress_percent !== null ? (
              <ProgressBar label={result.job.progress_text ?? "Running"} percent={result.job.progress_percent} />
            ) : null}
          </div>
        </div>
      ) : null}
      <div className="mt-2 grid gap-3 @md:grid-cols-2">
        <Side heading="Before" side={result.before} note={result.before_note} testId="change-result-before" />
        <Side heading="On this change" side={result.now} testId="change-result-now" />
      </div>
    </li>
  );
}

/** The panel of one developer's change: what changed, the tests picked and not picked with their reasons, Run the
 * picked tests (then Run again), the results before and now, and the flags. All wording is the backend's. Nothing here
 * runs unless the Run button is pressed. */
export function ChangePanelView({
  row,
  sending,
  onClose,
  onRun,
}: {
  row: ChangeRow | null;
  sending: boolean;
  onClose: () => void;
  onRun: (row: ChangeRow) => void;
}) {
  if (!row) return null;
  const panel = row.panel;
  const run = panel.run;
  return (
    <div data-testid="change-panel" data-change={row.id} className="contents">
      <DetailPanel
        open
        item={row.id}
        title={row.title}
        subtitle={
          // (the branch is in the box below: beside the header's buttons a long branch name would be broken between letters)
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="whitespace-nowrap font-mono">commit {row.commit}</span>
            {row.is_demo ? <DemoDataLabel /> : null}
          </span>
        }
        onClose={onClose}
      >
        <div className="space-y-5 text-sm">
          <div data-testid="change-status-box" className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
            <StatusChip label={row.status.word} tone={row.status.tone} wrap testId="change-panel-status" />
            {row.status.reason ? (
              <p data-testid="change-status-reason" className="mt-2 break-words text-sm text-slate-300">
                {row.status.reason}
              </p>
            ) : null}
            <p data-testid="change-branch" className="mt-2 break-words text-xs text-slate-400">
              Branch <span className="font-mono text-slate-300">{row.branch}</span>
            </p>
            <p className="mt-1 break-words text-xs text-slate-400">
              {[row.author ? `By ${row.author}` : null, row.when].filter(Boolean).join(", ")}
            </p>
            {panel.starts_from ? <p className="mt-1 break-words text-xs text-slate-400">{panel.starts_from}</p> : null}
            {panel.gives ? (
              <p data-testid="change-gives" className="mt-1 break-words text-xs text-slate-400">
                {panel.gives}
              </p>
            ) : null}
          </div>

          <div>
            <h3 className={H}>What changed</h3>
            <p data-testid="change-message" className="mb-2 whitespace-pre-wrap break-words text-[13px] text-slate-300">
              {panel.message}
            </p>
            <ul className="space-y-3">
              {panel.files.map((file) => (
                <li key={file.name} data-testid="change-file" className="min-w-0">
                  <p className="text-xs text-slate-300">
                    <span className="break-all font-mono text-slate-100">{file.name}</span>: {file.what}
                    {file.counts ? ` (${file.counts.charAt(0).toLowerCase()}${file.counts.slice(1)})` : ""}
                  </p>
                  {file.note ? <p className="mt-1 text-xs text-slate-400">{file.note}</p> : null}
                  {file.blocks.map((block, i) => (
                    <div key={i} data-testid="change-block" className="mt-2 min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
                      {block.before.length > 0 ? (
                        <>
                          <p className="mb-1 text-xs text-slate-400">Before</p>
                          <CodeLines lines={block.before} />
                        </>
                      ) : null}
                      {block.after.length > 0 ? (
                        <>
                          <p className={`mb-1 text-xs text-slate-400 ${block.before.length > 0 ? "mt-2.5" : ""}`}>After</p>
                          <CodeLines lines={block.after} />
                        </>
                      ) : null}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className={H}>Tests picked ({panel.picked.length})</h3>
            {panel.picked.length > 0 ? (
              <Tests tests={panel.picked} testId="change-picked" />
            ) : (
              <p data-testid="change-picked-empty" className="break-words text-sm text-slate-300">
                {panel.picked_empty ?? "None."}
              </p>
            )}
          </div>
          {panel.not_picked.length > 0 ? (
            <details data-testid="change-not-picked-box" className="rounded-lg border border-slate-800 p-3">
              <summary className="cursor-pointer text-[13px] font-semibold text-slate-100">Not picked ({panel.not_picked.length})</summary>
              <div className="mt-2">
                <Tests tests={panel.not_picked} testId="change-not-picked" />
              </div>
            </details>
          ) : null}

          <div data-testid="change-run" className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
            <PrimaryButton testId="change-run-button" disabled={!run.can} busy={sending} onClick={() => onRun(row)}>
              {run.label}
            </PrimaryButton>
            {run.blocked_reason ? (
              <p data-testid="change-run-blocked" className="mt-2 break-words text-sm text-slate-300">
                {run.blocked_reason}
              </p>
            ) : null}
            {run.note ? (
              <p data-testid="change-run-note" className="mt-2 break-words text-xs text-slate-400">
                {run.note}
              </p>
            ) : null}
            {panel.last_run ? (
              <p data-testid="change-last-run" className="mt-2 text-xs text-slate-400">
                Last run started {panel.last_run}.
              </p>
            ) : null}
          </div>

          {panel.results.length > 0 ? (
            <div>
              <h3 className={H}>Results: before, and on this change</h3>
              <ul data-testid="change-results" className="space-y-2">
                {panel.results.map((result) => (
                  <Result key={result.item_id} result={result} />
                ))}
              </ul>
            </div>
          ) : null}

          {panel.fix_line && panel.fix ? (
            <p data-testid="change-fix-line" className="break-words rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200">
              {panel.fix_line}{" "}
              <ItemLinkView link={panel.fix} testId="change-fix-link" className="text-sky-300 underline-offset-2 hover:underline">
                View in Fixes
              </ItemLinkView>
            </p>
          ) : null}

          {panel.flags.length > 0 ? (
            <div>
              <h3 className={H}>Flags ({row.flags_count})</h3>
              {panel.flags_note ? <p className="mb-2 text-xs text-slate-400">{panel.flags_note}</p> : null}
              <ul data-testid="change-flags" className="space-y-2">
                {panel.flags.map((flag, i) => (
                  <li key={i} data-testid="change-flag" className="min-w-0 rounded-lg border border-slate-700 bg-slate-900/70 p-3">
                    <p className="text-sm font-medium text-slate-100">{flag.title}</p>
                    <p className="mt-1 break-words text-[13px] text-slate-300">{flag.text}</p>
                    <p data-testid="change-flag-note" className="mt-1 text-[13px] text-slate-300">
                      {flag.note}
                    </p>
                    <p className="mt-1 break-words text-xs text-slate-400">
                      Why it is on the list:{" "}
                      {flag.source.url.startsWith("https://") ? (
                        <a href={flag.source.url} target="_blank" rel="noreferrer noopener" className="text-sky-300 underline-offset-2 hover:underline">
                          {flag.source.title}
                        </a>
                      ) : (
                        flag.source.title
                      )}
                    </p>
                  </li>
                ))}
              </ul>
              {panel.more_flags ? <p className="mt-2 text-xs text-slate-400">{panel.more_flags}</p> : null}
            </div>
          ) : null}
        </div>
      </DetailPanel>
    </div>
  );
}
