import { useRef, useState, type ReactNode, type RefObject } from "react";
import {
  errorMessage,
  type MigrationOptionKey,
  type MigrationSettingField,
  type MigrationSystem,
  type MigrationTrack,
} from "../../api";
import { ResultDetail } from "../lab/ResultDetail";
import { ChangeBox } from "../change/ChangeBox";
import { ProposalCard } from "../otto/ProposalCard";
import { AlsoNoticedList, ErrorBox, RichTextView, SourceTag, StatusView, WhereFromLine } from "../ui";
import { OptionCard, type SaveChoice } from "./OptionCard";
import { StatusPill } from "./parts";
import { CLOSED_SENTENCE, useReadOnly } from "../../readOnly";

function Box({
  children,
  testId,
  className = "border-slate-800",
}: {
  children: ReactNode;
  testId: string;
  className?: string;
}) {
  return (
    <section data-testid={testId} className={`rounded-xl border bg-slate-900/40 p-4 ${className}`}>
      {children}
    </section>
  );
}

const H3 = "text-[15px] font-semibold text-slate-100";

function TrackBox({ track }: { track: MigrationTrack }) {
  return (
    <div
      data-testid="migration-track"
      data-track={track.key}
      className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"
    >
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{track.title}</p>
      <div className="mt-1.5 flex flex-wrap items-start gap-3">
        <StatusPill status={track.status} large />
        <p data-testid="track-sentence" className="min-w-0 flex-1 basis-72 text-[15px] text-slate-100">
          {track.sentence}
        </p>
      </div>
      {track.facts.length > 0 ? (
        <dl className="mt-3 grid grid-cols-[minmax(0,15rem)_1fr] gap-x-4 gap-y-2 text-[13px]">
          {track.facts.map((fact, i) => (
            <div key={i} className="contents">
              <dt className="text-slate-400">{fact.label}</dt>
              <dd className="text-slate-200">
                <RichTextView parts={fact.value} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      <p data-testid="track-next" className="mt-3 border-t border-slate-800 pt-2.5 text-[13px] text-slate-200">
        <span className="font-semibold text-sky-200">{track.next_label}</span> <RichTextView parts={track.next} />
      </p>
      <p data-testid="track-why" className="mt-1 text-[13px] text-slate-400">
        <span className="font-medium text-slate-300">{track.why_label}</span> <RichTextView parts={track.why} />
      </p>
    </div>
  );
}

function Today({
  system,
  detailsOpen,
  onToggleDetails,
  detailsRef,
  onViewFix,
}: {
  system: MigrationSystem;
  detailsOpen: boolean;
  onToggleDetails: () => void;
  detailsRef: RefObject<HTMLDivElement | null>;
  onViewFix: (fixId: string) => void;
}) {
  const today = system.today;
  const tracks = system.tracks ?? [];
  const detailsId = `migration-details-${system.key}`;
  return (
    <Box testId="migration-today">
      <h3 className={H3}>{today.title}</h3>
      {/* 22 November 2026: where this status came from, with what that means for this system */}
      <div className="mt-2">
        <WhereFromLine tag={system.source_tag} />
      </div>
      <div className="mt-3 flex flex-wrap items-start gap-3">
        {system.measuring ? (
          <StatusView status={system.measuring} />
        ) : tracks.length > 0 ? (
          system.target_line ? (
            <p data-testid="target-line" className="text-sm text-slate-300">
              {system.target_line}
            </p>
          ) : null
        ) : (
          <>
            <StatusPill status={system.status} large />
            <p data-testid="today-sentence" className="min-w-0 flex-1 basis-72 text-base text-slate-100">
              {today.sentence}
            </p>
          </>
        )}
      </div>
      {today.file_note ? (
        <p
          data-testid="file-note"
          className="mt-3 rounded-md border border-slate-700 border-l-2 border-l-sky-400/50 bg-slate-900/60 px-3 py-2 text-[13px] text-slate-300"
        >
          {today.file_note}
        </p>
      ) : null}
      {today.facts.length > 0 ? (
        <dl data-testid="today-facts" className="mt-3 grid grid-cols-[minmax(0,15rem)_1fr] gap-x-4 gap-y-2 text-[13px]">
          {today.facts.map((fact, i) => (
            <div key={i} className="contents">
              <dt className="text-slate-400">{fact.label}</dt>
              <dd className="text-slate-200">
                <RichTextView parts={fact.value} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {tracks.length > 0 && !system.measuring ? (
        <div className="mt-3 flex flex-col gap-3">
          {tracks.map((track) => (
            <TrackBox key={track.key} track={track} />
          ))}
        </div>
      ) : null}
      {(system.also_noticed ?? []).length > 0 ? (
        <div className="mt-3">
          <AlsoNoticedList title={system.also_noticed_title ?? ""} items={system.also_noticed ?? []} />
        </div>
      ) : null}
      {today.control_line ? (
        <p data-testid="today-control" className="mt-3 text-xs text-slate-400">
          {today.control_line}
        </p>
      ) : null}
      {today.result ? (
        <div ref={detailsRef} className="mt-3 border-t border-slate-800 pt-3">
          <button
            type="button"
            aria-expanded={detailsOpen}
            aria-controls={detailsId}
            onClick={onToggleDetails}
            className="flex items-center gap-2 rounded text-left text-sm text-slate-300 hover:text-slate-100"
          >
            <span aria-hidden="true" className="font-mono text-xs">
              {detailsOpen ? "▾" : "▸"}
            </span>
            {today.details_label}
          </button>
          {detailsOpen ? (
            <div id={detailsId}>
              <ResultDetail result={today.result} busy={false} onViewFix={onViewFix} />
            </div>
          ) : null}
        </div>
      ) : null}
    </Box>
  );
}

/** Phase 5c: Otto's proposed changes to this system's plan (something to fix first, from a result). Otto proposes; a
 * person decides on each card. A decision changes no status and no measurement: afterwards the screen reads its own
 * view again. Every word is the view's. */
function OttoPlan({
  block,
  planId,
  onChanged,
}: {
  block: NonNullable<MigrationSystem["otto"]>;
  planId: number;
  onChanged: () => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  return (
    <Box testId="system-otto">
      <h3 className={H3}>{block.title}</h3>
      <p data-testid="system-otto-note" className="mt-0.5 text-sm text-slate-300">
        {block.note}
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {block.proposals.map((proposal) => (
          <ProposalCard
            key={proposal.id}
            planId={planId}
            proposal={proposal}
            onDecided={() => {
              setError(null);
              onChanged().catch((e: unknown) => setError(errorMessage(e)));
            }}
          />
        ))}
      </div>
      {error ? (
        <div className="mt-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
    </Box>
  );
}

function Settings({
  system,
  busy,
  onChange,
}: {
  system: MigrationSystem;
  busy: boolean;
  onChange: (field: MigrationSettingField["field"], value: string) => void;
}) {
  const settings = system.settings;
  const closed = useReadOnly(); // phase 5a: a closed assessment is read-only
  return (
    <Box testId="migration-settings">
      <h3 className={H3}>{settings.title}</h3>
      <p className="mt-0.5 text-sm text-slate-300">{settings.intro}</p>
      <div className="mt-3 grid gap-4 md:grid-cols-3">
        {settings.fields.map((field) => {
          const id = `setting-${system.key}-${field.field}`;
          return (
            <div key={field.field} data-testid="migration-setting" data-field={field.field}>
              <label htmlFor={id} className="block text-xs text-slate-400">
                {field.label}
              </label>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <select
                  id={id}
                  value={field.value}
                  disabled={!field.enabled || busy || closed}
                  title={closed ? CLOSED_SENTENCE : undefined}
                  aria-describedby={`${id}-help ${id}-source`}
                  onChange={(e) => onChange(field.field, e.target.value)}
                  className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {field.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <span id={`${id}-source`} data-testid="setting-source">
                  <SourceTag>{field.source}</SourceTag>
                </span>
              </div>
              <p id={`${id}-help`} className="mt-1 text-xs text-slate-500">
                {field.help}
              </p>
            </div>
          );
        })}
      </div>
    </Box>
  );
}

function Cost({ cost }: { cost: NonNullable<MigrationSystem["cost"]> }) {
  const [rowLabel, ...heads] = cost.columns;
  return (
    <Box testId="migration-cost">
      <h3 className={H3}>{cost.title}</h3>
      <p className="mt-0.5 text-sm text-slate-300">{cost.intro}</p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 px-3 py-1">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr>
              <th
                scope="col"
                className="border-b border-slate-800 px-2.5 py-1.5 text-left align-bottom text-xs font-medium uppercase tracking-wide text-slate-400"
              >
                {rowLabel ?? ""}
              </th>
              {heads.map((head, i) => (
                <th
                  key={i}
                  scope="col"
                  className="border-b border-slate-800 px-2.5 py-1.5 text-left align-bottom text-xs font-medium uppercase tracking-wide text-slate-400"
                >
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cost.rows.map((row, r) => (
              <tr key={r} className="border-b border-slate-800 last:border-b-0">
                <th scope="row" className="px-2.5 py-2 text-left align-top font-medium text-slate-100">
                  {row.label}
                </th>
                {row.cells.map((cell, c) => (
                  <td key={c} className="px-2.5 py-2 align-top text-slate-200">
                    <RichTextView parts={cell} mono="font-mono" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cost.note ? <p className="mt-2 text-xs text-slate-400">{cost.note}</p> : null}
    </Box>
  );
}

function Recommendation({ system, onSeeEvidence }: { system: MigrationSystem; onSeeEvidence: () => void }) {
  const rec = system.recommendation;
  const none = rec.none_text !== null;
  return (
    <Box
      testId="migration-recommendation"
      className={none ? "border-dashed border-slate-600" : "border-sky-400/60 bg-sky-400/5"}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className={H3}>{rec.title}</h3>
        {rec.tag ? <SourceTag>{rec.tag}</SourceTag> : null}
      </div>
      {rec.none_text ? (
        <p data-testid="recommendation-none" className="mt-2 text-sm text-slate-300">
          {rec.none_text}
        </p>
      ) : rec.reasons.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-200 marker:text-slate-500">
          {rec.reasons.map((reason, i) => (
            <li key={i} data-testid="recommendation-reason">
              <RichTextView parts={reason} />
            </li>
          ))}
        </ul>
      ) : null}
      {rec.evidence || (rec.evidence_link && system.today.result) ? (
        <p data-testid="recommendation-evidence" className="mt-2 text-[13px] text-slate-300">
          {rec.evidence ? <RichTextView parts={rec.evidence} /> : null}
          {rec.evidence_link && system.today.result ? (
            <>
              {" "}
              <button
                type="button"
                onClick={onSeeEvidence}
                className="whitespace-nowrap rounded font-medium text-sky-300 underline decoration-sky-300/40 underline-offset-2 hover:text-sky-200"
              >
                {rec.evidence_link}
              </button>
            </>
          ) : null}
        </p>
      ) : null}
    </Box>
  );
}

interface Props {
  system: MigrationSystem;
  /** A button's call is on its way, or a measurement runs: buttons wait. */
  busy: boolean;
  detailsOpen: boolean;
  onDetailsOpen: (open: boolean) => void;
  /** The option whose choose box is open in this system, if any. */
  openOption: MigrationOptionKey | null;
  onOpenOption: (option: MigrationOptionKey | null) => void;
  onSetting: (field: MigrationSettingField["field"], value: string) => void;
  onSaveChoice: (option: MigrationOptionKey) => SaveChoice;
  onViewFix: (fixId: string) => void;
  /** After a change-box call went through: load the view again and tell the app. */
  onChanged: () => Promise<void>;
  planId: number;
}

/** The selected system on the Systems view, top to bottom as the view sends it. */
export function SystemDetail({
  system,
  busy,
  detailsOpen,
  onDetailsOpen,
  openOption,
  onOpenOption,
  onSetting,
  onSaveChoice,
  onViewFix,
  onChanged,
  planId,
}: Props) {
  const detailsRef = useRef<HTMLDivElement | null>(null);

  function seeEvidence() {
    onDetailsOpen(true);
    // jsdom has no scrollIntoView; a browser always does.
    detailsRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  const hasOptions = system.options.length > 0;

  return (
    <div data-testid="migration-system" data-system={system.key} className="flex min-w-0 flex-col gap-3">
      {/* The panel's own heading shows the kind of system; the name is the heading of this box. */}
      <h2 className="text-lg font-semibold text-slate-50">{system.name}</h2>
      <Today
        system={system}
        detailsOpen={detailsOpen}
        onToggleDetails={() => onDetailsOpen(!detailsOpen)}
        detailsRef={detailsRef}
        onViewFix={onViewFix}
      />
      {/* Right under the tracks: what Otto proposes to fix first on one of them. */}
      {system.otto ? <OttoPlan block={system.otto} planId={planId} onChanged={onChanged} /> : null}
      <Settings system={system} busy={busy} onChange={onSetting} />
      {system.cost ? <Cost cost={system.cost} /> : null}
      <Recommendation system={system} onSeeEvidence={seeEvidence} />
      {system.change ? (
        <ChangeBox change={system.change} planId={planId} onChanged={onChanged} onViewFix={onViewFix} />
      ) : null}
      {hasOptions ? (
        <section data-testid="migration-options" aria-labelledby={`options-${system.key}`}>
          <h3 id={`options-${system.key}`} className={`${H3} mb-2 px-1`}>
            {system.options_title}
          </h3>
          <div className="grid items-start gap-3 md:grid-cols-2">
            {system.options.map((option) => (
              <OptionCard
                key={option.key}
                option={option}
                open={openOption === option.key}
                busy={busy}
                onOpen={() => onOpenOption(option.key)}
                onCancel={() => onOpenOption(null)}
                onSave={onSaveChoice(option.key)}
                onViewFix={onViewFix}
              />
            ))}
          </div>
          {system.choice ? (
            <div data-testid="migration-choice" className="mt-3 rounded-xl border border-slate-400 bg-slate-800/60 p-4">
              <p className="text-sm font-semibold text-slate-50">{system.choice.line}</p>
              {system.choice.history.length > 0 ? (
                <ul className="mt-1.5 space-y-0.5 text-[13px] text-slate-300">
                  {system.choice.history.map((line, i) => (
                    <li key={i} data-testid="choice-history">
                      {line}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          <p data-testid="choices-note" className="mt-2 px-1 text-xs text-slate-400">
            {system.choices_note}
          </p>
        </section>
      ) : null}
    </div>
  );
}
