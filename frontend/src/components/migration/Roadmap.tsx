import type { EvidenceExport, MigrationRoadmapBand, MigrationView } from "../../api";
import { DownloadStatus } from "../evidenceDownload";
import { usePanelOpen } from "../layout";
import { FromOttoTag } from "../otto/ProposalCard";
import { SecondaryButton, SourceTag } from "../ui";
import { LineView } from "./parts";

const BAND_LOOKS: Record<MigrationRoadmapBand["look"], string> = {
  plain: "border-slate-800",
  highlight: "border-sky-400/60",
  dashed: "border-dashed border-slate-600",
};

interface Props {
  view: MigrationView;
  busy: boolean;
  exported: EvidenceExport | null;
  onDownload: () => void;
  onViewFix: (fixId: string) => void;
  /** The system whose detail panel is open, and the way to open another. */
  selectedKey: string | null;
  onOpenSystem: (systemKey: string) => void;
}

/** The plan, band by band, exactly as sent. A row opens that system's detail in the panel beside the plan. */
export function Roadmap({ view, busy, exported, onDownload, onViewFix, selectedKey, onOpenSystem }: Props) {
  const roadmap = view.roadmap;
  const download = roadmap.download;
  // Phase 5b: beside the open panel, a row is the system with its track, the plan, and the note only where it points to
  // a fix (a blocker); the full row comes back when the panel closes.
  const compact = usePanelOpen();
  return (
    <div data-testid="migration-roadmap" data-compact={compact || undefined}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p data-testid="roadmap-intro" className="max-w-2xl text-sm text-slate-300">
          {roadmap.intro}
        </p>
        <SecondaryButton disabled={busy || !download.can_start} onClick={onDownload}>
          {download.label}
        </SecondaryButton>
      </div>
      {!download.can_start && download.blocked_reason ? (
        <p data-testid="download-blocked" className="mt-2 text-xs text-slate-400">
          {download.blocked_reason}
        </p>
      ) : null}
      {exported ? <DownloadStatus exported={exported} /> : null}

      <div className="mt-4 flex flex-col gap-3">
        {roadmap.bands.map((band) => (
          <section
            key={band.key}
            data-testid="roadmap-band"
            data-band={band.key}
            data-look={band.look}
            aria-labelledby={`band-${band.key}`}
            className={`rounded-xl border bg-slate-900/40 p-4 ${BAND_LOOKS[band.look] ?? BAND_LOOKS.plain}`}
          >
            <div className="flex flex-wrap items-baseline gap-x-3">
              <h2 id={`band-${band.key}`} className="text-[15px] font-semibold text-slate-100">
                {band.title}
              </h2>
              <p className="text-[13px] text-slate-400">{band.sub}</p>
            </div>
            {/* The four columns need room; in a narrow plan (the detail panel open beside it) each row stacks. */}
            <ul className="@container mt-2">
              {band.rows.map((row) => (
                <li
                  key={`${row.system_key}:${row.track ?? ""}`}
                  data-testid="roadmap-row"
                  data-system={row.system_key}
                  onClick={() => onOpenSystem(row.system_key)}
                  className={`grid cursor-pointer gap-x-4 gap-y-1 border-t border-slate-800 px-2 py-2 first:border-t-0 hover:bg-slate-800/40 ${
                    compact
                      ? "grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
                      : "@2xl:grid-cols-[minmax(0,200px)_minmax(0,130px)_minmax(0,230px)_minmax(0,1fr)]"
                  } ${
                    row.system_key === selectedKey
                      ? "bg-sky-400/[0.07] shadow-[inset_2px_0_0_var(--color-sky-400)]"
                      : ""
                  }`}
                >
                  <button
                    type="button"
                    aria-current={row.system_key === selectedKey ? "true" : undefined}
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenSystem(row.system_key);
                    }}
                    className="block self-start text-left"
                  >
                    {compact ? null : <span className="block text-xs text-slate-400">{row.kind_label}</span>}
                    <span className="block text-sm font-semibold text-slate-100">{row.name}</span>
                    {compact && row.track ? (
                      <span data-testid="roadmap-track" className="block text-xs text-slate-400">
                        {row.track}
                      </span>
                    ) : null}
                  </button>
                  {compact ? null : (
                    <span data-testid="roadmap-track" className="text-[13px] text-slate-300">
                      {row.track ?? ""}
                    </span>
                  )}
                  <span className="min-w-0 text-sm text-slate-200">
                    {row.option}
                    {row.plan_tag ? (
                      compact ? (
                        <span className="mt-1 block text-xs text-slate-400">{row.plan_tag}</span>
                      ) : (
                        <>
                          {" "}
                          <SourceTag>{row.plan_tag}</SourceTag>
                        </>
                      )
                    ) : null}
                  </span>
                  {!compact || row.note.fix_id ? (
                    <span
                      data-testid="roadmap-note"
                      className={`text-[13px] text-slate-300 ${compact ? "col-span-2" : ""}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <LineView line={row.note} onViewFix={onViewFix} />
                    </span>
                  ) : null}
                  {/* Phase 5c: Otto has a proposal for this system: its tag and the view's own words, on a line of its
                      own under the row in both forms. It is not a button: the row opens the system's panel, where the
                      decision buttons are. */}
                  {row.otto ? (
                    <span
                      data-testid="roadmap-otto"
                      data-waiting={row.otto.waiting}
                      data-tone={row.otto.tone}
                      className={`flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs ${compact ? "col-span-2" : "@2xl:col-span-4"} ${
                        row.otto.waiting > 0 ? "font-medium text-slate-100" : "text-slate-400"
                      }`}
                    >
                      <FromOttoTag label={row.otto.label} testId="roadmap-otto-label" />
                      <span className="min-w-0 break-words">{row.otto.text}</span>
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
