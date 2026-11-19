import type { AdvisoryHereRow, AdvisoryRow, OttoProposal } from "../../api";
import { DetailPanel } from "../layout";
import { ProposalCard } from "../otto/ProposalCard";
import { ItemLinkView, RelatedBlock, useRelated } from "../related";
import { formatTime, StatusChip } from "../ui";
import { BLOCK, BLOCK_TITLE, LedgerView, QuoteView, ShortHash, SourcesView, TrialView } from "./parts";

const DT = "text-xs text-slate-500";
const DD = "min-w-0 break-words text-slate-200";
/** A name and its words: one under the other in a narrow panel, side by side in a wide one. */
const PAIR = "grid gap-x-3 gap-y-0.5 @md:grid-cols-[8.5rem_minmax(0,1fr)]";

/** The advisory's check for one signing program of this assessment. First Otto's proposal of it, which a person
 * accepts or rejects (the shared proposal card: its state, who decided and when, and the buttons); then where the
 * check stands, or the reviewer's result as Evidence words it, with the way to the check and to its evidence. */
function HereRow({ planId, row, onDecided }: { planId: number; row: AdvisoryHereRow; onDecided: (next: OttoProposal) => void }) {
  const result = row.result;
  const proposal = row.proposal;
  // Before a check is in the plan the view's status is the proposal's own word, which the card already shows.
  const status = row.status && row.status !== proposal?.status.word ? row.status : null;
  return (
    <li data-testid="advisory-here-row" data-program={row.program} className="min-w-0 border-t border-slate-800 pt-3 first:border-t-0 first:pt-0">
      <p className="break-words font-medium text-slate-100">{row.program}</p>
      {proposal ? (
        <div className="mt-2">
          {/* The program's name heads this row, so the card needs no title of its own. */}
          <ProposalCard planId={planId} proposal={proposal} onDecided={onDecided} showTitle={false} />
        </div>
      ) : null}
      {result ? (
        <div className="mt-2">
          <StatusChip label={result.label} tone={result.tone} wrap testId="advisory-here-result" />
          {result.ran_on ? (
            // After a retest the newest result is of another version than the one this row is named for: said first.
            <p data-testid="advisory-here-ran-on" className="mt-1.5 break-words font-medium text-slate-100">
              {result.ran_on}
            </p>
          ) : null}
          <p className="mt-1.5 break-words text-slate-200">{result.plain}</p>
          {result.component || result.finished_at ? (
            <p className="mt-1 flex flex-wrap gap-x-2 text-xs text-slate-400">
              {result.component ? <span className="break-words">{result.component}</span> : null}
              {result.finished_at ? <time dateTime={result.finished_at}>{formatTime(result.finished_at)}</time> : null}
            </p>
          ) : null}
        </div>
      ) : status ? (
        <p data-testid="advisory-here-status" className="mt-1.5 break-words text-slate-400">
          {status}
        </p>
      ) : null}
      {row.checks_link || row.evidence_link ? (
        <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {row.checks_link ? (
            <ItemLinkView link={row.checks_link} testId="open-in-checks">
              Open in Checks
            </ItemLinkView>
          ) : null}
          {row.evidence_link ? (
            <ItemLinkView link={row.evidence_link} testId="see-the-evidence">
              See the evidence
            </ItemLinkView>
          ) : null}
        </p>
      ) : null}
      {row.ledger ? (
        <div className="mt-2">
          <LedgerView ledger={row.ledger} />
        </div>
      ) : null}
    </li>
  );
}

/** Phase 5c: one advisory in the side panel, in the view's own words and order: what it says, the publisher's own
 * line and sources, its test (or why it has none), Otto's proposed check for each program of this assessment (with
 * Accept and Reject, each decided by itself) and that check's result, the fix, what Otto asked Claude, and Related.
 * A decision is a person's click and runs nothing; the panel itself starts nothing and words no result. */
export function AdvisoryPanel({
  planId,
  row,
  onClose,
  onDecided,
}: {
  planId: number;
  row: AdvisoryRow | null;
  onClose: () => void;
  /** A decision on one of this advisory's proposals was recorded: the page reads its view again. */
  onDecided: (next: OttoProposal) => void;
}) {
  const related = useRelated(planId, row?.panel.related_key ?? null);
  if (!row) return null;
  const panel = row.panel;
  const test = panel.test;
  const noTest = panel.no_test;
  return (
    // This wrapper has no box of its own: it names the whole panel (its heading and close button too) for a link or
    // a test to find, and the panel lays itself out beside the table as on every other page.
    <div data-testid="advisory-panel" data-advisory={row.id} className="contents">
      <DetailPanel
        open
        item={row.id}
        title={row.name}
        subtitle={
          // The table drops its Published column while the panel is open, so the day is said here too.
          <span className="flex flex-wrap gap-x-2">
            <span className="font-mono">{row.id}</span>
            {row.published_text ? <span data-testid="advisory-published">Published {row.published_text}</span> : null}
          </span>
        }
        onClose={onClose}
      >
        <div className="space-y-4 text-sm">
          <p data-testid="advisory-sentence" className="break-words text-slate-200">
            {panel.sentence}
          </p>

          {panel.publisher || panel.sources.length > 0 ? (
            <div className="min-w-0">
              {panel.publisher ? <QuoteView quote={panel.publisher} testId="advisory-publisher" /> : null}
              <SourcesView sources={panel.sources} />
            </div>
          ) : null}

          {panel.affected ? (
            <div data-testid="advisory-affected" className="min-w-0 space-y-2">
              <p className="break-words text-slate-200">{panel.affected.line}</p>
              <QuoteView quote={panel.affected.quote} />
            </div>
          ) : null}

          {panel.notes ? (
            // Claude's own words from reading the advisory: long, and not a result, so they stay folded under their name.
            <details data-testid="advisory-notes" className="min-w-0 text-[13px] text-slate-300">
              <summary className="cursor-pointer text-xs font-medium text-slate-300 hover:text-slate-100">{panel.notes.title}</summary>
              <p data-testid="advisory-notes-kind" className="mt-1.5 break-words">
                {panel.notes.kind_line}
              </p>
              {panel.notes.text ? (
                <p data-testid="advisory-notes-text" className="mt-1.5 break-words">
                  {panel.notes.text}
                </p>
              ) : null}
              <p className="mt-1.5 break-words text-xs text-slate-400">{panel.notes.caption}</p>
            </details>
          ) : null}

          {panel.also_known_as.length > 0 ? (
            <p data-testid="advisory-also-known-as" className="break-words text-slate-300">
              <span className={DT}>Also known as</span> <span className="font-mono text-[13px]">{panel.also_known_as.join(", ")}</span>
            </p>
          ) : null}

          {test ? (
            <section data-testid="advisory-test-block" aria-label={test.title} className={BLOCK}>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className={BLOCK_TITLE}>{test.title}</h3>
                <StatusChip label={row.test.label} tone={row.test.tone} size="sm" wrap />
              </div>
              <p data-testid="advisory-test-reason" className="mt-1.5 break-words text-slate-300">
                {row.test.reason}
              </p>
              {/* The view sends each of these as a sentence without a name; the names follow the ones Evidence shows for a locked test. */}
              <dl className="mt-3 space-y-2 text-[13px]">
                {(
                  [
                    ["Question", test.question],
                    ["Cases", test.cases_line],
                    ["Control", test.control],
                    ["Pass/fail rule", test.rule],
                  ] as const
                ).map(([name, words]) => (
                  <div key={name} className={PAIR}>
                    <dt className={DT}>{name}</dt>
                    <dd className={DD}>{words}</dd>
                  </div>
                ))}
                <div className={PAIR}>
                  <dt className={DT}>Design fingerprint</dt>
                  <dd className={DD}>
                    <ShortHash value={test.design_fingerprint} />
                  </dd>
                </div>
              </dl>
              <div className="mt-3">
                <TrialView trial={test.trial} />
              </div>
              <div className="mt-3">
                <LedgerView ledger={test.ledger} />
              </div>
            </section>
          ) : null}

          {noTest ? (
            <section data-testid="advisory-no-test" aria-label={noTest.label} className={BLOCK}>
              <StatusChip label={noTest.label} tone={row.test.tone} size="sm" wrap />
              <p data-testid="advisory-test-reason" className="mt-1.5 break-words text-slate-300">
                {noTest.reason}
              </p>
              {noTest.trial ? (
                <div className="mt-3">
                  <TrialView trial={noTest.trial} />
                </div>
              ) : null}
              {noTest.ledger ? (
                <div className="mt-3">
                  <LedgerView ledger={noTest.ledger} />
                </div>
              ) : null}
            </section>
          ) : null}

          <section data-testid="advisory-here" aria-label={panel.here.title} className={BLOCK}>
            <h3 className={BLOCK_TITLE}>{panel.here.title}</h3>
            {panel.here.note ? (
              <p data-testid="advisory-here-note" className="mt-1.5 break-words text-xs text-slate-400">
                {panel.here.note}
              </p>
            ) : null}
            {panel.here.rows.length > 0 ? (
              <ul className="mt-2 space-y-3">
                {panel.here.rows.map((h, i) => (
                  <HereRow key={`${h.program}-${i}`} planId={planId} row={h} onDecided={onDecided} />
                ))}
              </ul>
            ) : panel.here.empty ? (
              <p data-testid="advisory-here-empty" className="mt-2 break-words text-slate-400">
                {panel.here.empty}
              </p>
            ) : null}
          </section>

          <section data-testid="advisory-fix" data-state={panel.fix.state} aria-label={panel.fix.title} className={BLOCK}>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className={BLOCK_TITLE}>{panel.fix.title}</h3>
              {panel.fix.label ? (
                <span
                  data-testid="advisory-fix-label"
                  className="inline-block whitespace-nowrap rounded border border-slate-500 bg-slate-700/40 px-2 py-0.5 text-xs font-medium text-slate-100"
                >
                  {panel.fix.label}
                </span>
              ) : null}
            </div>
            <div className="mt-2 space-y-1.5 text-slate-200">
              {panel.fix.lines.map((line, i) => (
                <p key={i} className="break-words">
                  {line}
                </p>
              ))}
            </div>
            {panel.fix.quote ? (
              <div className="mt-3">
                <QuoteView quote={panel.fix.quote} />
              </div>
            ) : null}
            {panel.fix.here ? (
              <p data-testid="advisory-fix-here" className="mt-3 break-words text-slate-300">
                {panel.fix.here.line}{" "}
                <ItemLinkView link={panel.fix.here.link} testId="advisory-fix-link">
                  {panel.fix.here.label}
                </ItemLinkView>
              </p>
            ) : null}
          </section>

          <details data-testid="advisory-claude" className={BLOCK}>
            <summary className={`cursor-pointer hover:text-slate-200 ${BLOCK_TITLE}`}>{panel.claude.title}</summary>
            <ol className="mt-2 space-y-2">
              {panel.claude.steps.map((s, i) => (
                <li key={i} data-testid="advisory-step" data-source={s.source} className="text-[13px] text-slate-300">
                  <span className="block break-words">{s.line}</span>
                  <span className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
                    <span>
                      Prompt SHA-256 <ShortHash value={s.prompt_sha256} />
                    </span>
                    <span>
                      Answer SHA-256 <ShortHash value={s.answer_sha256} />
                    </span>
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-2 break-words text-xs text-slate-400">{panel.claude.note}</p>
          </details>

          {related && related.length > 0 ? (
            <div data-testid="advisory-related">
              <RelatedBlock lines={related} />
            </div>
          ) : null}
        </div>
      </DetailPanel>
    </div>
  );
}
