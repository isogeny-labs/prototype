import type { EvidenceExport, MigrationRoadmapBand, MigrationView } from "../../api";
import { DownloadStatus } from "../evidenceDownload";
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
}

/** The plan, band by band, exactly as sent. Pressing a system's name opens it in the Systems view. */
export function Roadmap({ view, busy, exported, onDownload, onViewFix }: Props) {
  const roadmap = view.roadmap;
  const download = roadmap.download;
  return (
    <div data-testid="migration-roadmap">
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
            <ul className="mt-2">
              {band.rows.map((row) => (
                <li
                  key={row.system_key}
                  data-testid="roadmap-row"
                  data-system={row.system_key}
                  className="grid gap-x-4 gap-y-1 border-t border-slate-800 py-2.5 first:border-t-0 md:grid-cols-[210px_250px_1fr]"
                >
                  <span>
                    <span className="block text-xs text-slate-400">{row.kind_label}</span>
                    <span className="block text-sm font-semibold text-slate-100">{row.name}</span>
                  </span>
                  <span className="text-sm text-slate-200">
                    {row.option}
                    {row.plan_tag ? (
                      <>
                        {" "}
                        <SourceTag>{row.plan_tag}</SourceTag>
                      </>
                    ) : null}
                  </span>
                  <span data-testid="roadmap-note" className="text-[13px] text-slate-300">
                    <LineView line={row.note} onViewFix={onViewFix} />
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
