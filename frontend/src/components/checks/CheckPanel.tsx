import { useEffect, useState } from "react";
import { api, errorMessage, type CheckDetail, type CheckRow, type CheckRun, type SameMeasurement } from "../../api";
import { DetailPanel } from "../layout";
import { FromOttoTag } from "../otto/ProposalCard";
import { ItemLinkView, RelatedBlock } from "../related";
import { ErrorBox, formatTime, ResultBadge, StatusView, WhereFromLine } from "../ui";

/** Phase 5b: one check in the side panel: its newest result in the words of the page it came from, where it came
 * from (Open where it started), See the evidence, the earlier runs, and Related. It starts nothing. */
export function CheckPanel({
  planId,
  check,
  onClose,
  children,
}: {
  planId: number;
  check: CheckRow | null;
  onClose: () => void;
  /** Extra content drawn under the summary (Evidence draws the run's full record here). */
  children?: (detail: CheckDetail) => React.ReactNode;
}) {
  const [detail, setDetail] = useState<CheckDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const id = check?.id ?? null;
  const stamp = check ? `${check.last_run_at ?? ""}:${check.runs}:${check.state}` : "";
  useEffect(() => {
    let live = true;
    setError(null);
    if (id === null) {
      setDetail(null);
      return;
    }
    api
      .getCheck(planId, id)
      .then((d) => {
        if (live) setDetail(d);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId, id, stamp]);

  const shown = detail && detail.check.id === id ? detail : null;
  return (
    <DetailPanel
      open={check !== null}
      item={check?.id ?? null}
      title={check?.name ?? ""}
      subtitle={check?.ran_on}
      onClose={onClose}
      testId="detail-panel"
    >
      {check ? (
        <div data-testid="check-panel" data-check={check.id} className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            {check.result ? <ResultBadge label={check.result.label} tone={check.result.tone} /> : null}
            {check.status ? <StatusView status={check.status} /> : null}
            {!check.result && !check.status ? <span className="text-slate-400">Not run yet.</span> : null}
          </div>
          {/* 22 November 2026: where it came from, with what that means for this check */}
          {check.result ? <WhereFromLine tag={check.source_tag} /> : null}
          {/* Phase 5c: an advisory check came from one of Otto's proposals: the tag and its advisory, in the view's words. */}
          {check.from_otto ? (
            <p data-testid="check-from-otto-line" className="flex min-w-0 flex-wrap items-center gap-2">
              <FromOttoTag label={check.from_otto.label} />
              <ItemLinkView link={check.from_otto.link} testId="check-from-otto">
                {check.from_otto.advisory}
              </ItemLinkView>
            </p>
          ) : null}
          {check.plain ? <p className="text-slate-200">{check.plain}</p> : null}
          <dl className="grid gap-2 @md:grid-cols-[9rem_minmax(0,1fr)]">
            <dt className="text-xs text-slate-500">Came from</dt>
            <dd>
              {check.came_from.label} ·{" "}
              <ItemLinkView link={check.link} testId="open-where-started">
                Open where it started
              </ItemLinkView>
            </dd>
            <dt className="text-xs text-slate-500">Evidence</dt>
            <dd>
              <ItemLinkView link={check.evidence_link} testId="see-the-evidence">
                See the evidence
              </ItemLinkView>
            </dd>
            {check.last_run_at ? (
              <>
                <dt className="text-xs text-slate-500">Last run</dt>
                <dd>
                  {formatTime(check.last_run_at)} · {check.runs} {check.runs === 1 ? "run" : "runs"}
                </dd>
              </>
            ) : null}
          </dl>
          {(check.same_as ?? []).length > 0 ? (
            <p data-testid="same-measurement" className="text-slate-300">
              The same measurement as{" "}
              {(check.same_as ?? []).map((o, i) => (
                <span key={o.id}>
                  {i > 0 ? ", " : ""}
                  <ItemLinkView link={o.link}>
                    {o.name} on {o.ran_on}
                  </ItemLinkView>{" "}
                  <span className="text-slate-500">({o.group_label})</span>
                </span>
              ))}
              . Each keeps its own run and its own result.
            </p>
          ) : null}
          {error ? <ErrorBox>{error}</ErrorBox> : null}
          {shown && children ? children(shown) : null}
          {shown ? <EarlierRuns runs={shown.runs} /> : null}
          {shown ? <RelatedBlock lines={shown.related} /> : null}
        </div>
      ) : null}
    </DetailPanel>
  );
}

/** A group's foot line: the checks of another group that also relate to this one ("Also relates to this group"),
 * each a link (on Checks to the check, on Evidence to its evidence). Counted in their own group only. */
export function AlsoChecks({ items, which }: { items: SameMeasurement[]; which: "link" | "evidence_link" }) {
  if (items.length === 0) return null;
  return (
    <span>
      Also relates to this group:{" "}
      {items.map((a, i) => (
        <span key={a.id}>
          {i > 0 ? ", " : ""}
          <ItemLinkView link={a[which]} testId="also-link">
            {a.name} on {a.ran_on}
          </ItemLinkView>{" "}
          (in {a.group_label}; the same measurement as Measure status)
        </span>
      ))}
    </span>
  );
}

/** Every run of one check, newest first: when, where it came from, its result, and the run's fingerprint. */
export function EarlierRuns({ runs }: { runs: CheckRun[] }) {
  if (runs.length === 0) return null;
  return (
    <section data-testid="earlier-runs" aria-label="Every run" className="rounded-lg border border-slate-800 p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Every run, newest first</h3>
      <ol className="space-y-1.5">
        {runs.map((r, i) => (
          <li
            key={`${r.run_id ?? r.verify_run_id ?? i}`}
            className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-300"
          >
            {r.label ? <ResultBadge label={r.label} tone={r.tone} /> : null}
            <span>{r.at ? formatTime(r.at) : ""}</span>
            <span className="text-slate-500">· {r.came_from}</span>
            {r.fingerprint ? (
              <span className="font-mono text-slate-500" title={r.fingerprint}>
                · {r.fingerprint.slice(0, 12)}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
