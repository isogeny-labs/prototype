import { useEffect, useState } from "react";
import { api, errorMessage, type ObservatoryPanel, type ObservatoryPanelCheck } from "../../api";
import { HistoryFold } from "../evidence/HistoryFold";
import { DetailPanel } from "../layout";
import { ProofFold, ProofPart } from "../proof";
import { ItemLinkView, RelatedFold } from "../related";
import { ErrorBox, StatusChip, WhereFromLine, WhereFromTag, formatTime } from "../ui";

/** One check of the box: its name, the word of its own page, its plain sentence and the ways to where it lives. */
function Check({ check, tagged }: { check: ObservatoryPanelCheck; tagged: boolean }) {
  return (
    <li
      data-testid="box-check"
      data-check={check.id}
      className="border-t border-slate-800 py-2.5 first:border-t-0 first:pt-0"
    >
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-medium text-slate-100">{check.name}</span>
        {check.checked && check.tone ? (
          <StatusChip label={check.word} tone={check.tone} size="sm" wrap testId="box-check-word" />
        ) : (
          <span data-testid="box-check-word" className="text-xs text-slate-500">
            {check.running ? "Running" : check.word}
          </span>
        )}
        {check.came_from ? <span className="text-xs text-slate-400">{check.came_from}</span> : null}
        {tagged ? null : <WhereFromTag tag={check.tag} />}
        {check.at ? (
          <time dateTime={check.at} className="text-xs text-slate-500">
            {formatTime(check.at)}
          </time>
        ) : null}
      </p>
      {check.plain ? <p className="mt-1 break-words text-[13px] text-slate-300">{check.plain}</p> : null}
      {check.next ? <p className="mt-1 break-words text-[13px] text-slate-300">{check.next}</p> : null}
      {check.beside.map((beside, i) => (
        // (beside the first result, never in its place)
        <p
          key={i}
          data-testid="box-check-beside"
          className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]"
        >
          <span className="text-slate-400">{beside.label}</span>
          <StatusChip label={beside.word} tone={beside.tone} size="sm" wrap />
          <WhereFromTag tag={beside.tag} />
          {beside.plain ? <span className="basis-full text-slate-300">{beside.plain}</span> : null}
          <ItemLinkView link={beside.link}>Open</ItemLinkView>
        </p>
      ))}
      {check.fix ? (
        <p data-testid="box-check-fix" className="mt-1.5 text-[13px] text-slate-300">
          {check.fix.text}{" "}
          <ItemLinkView link={check.fix.link} testId="box-check-fix-link">
            {check.fix.label}
          </ItemLinkView>
        </p>
      ) : null}
      {check.links.length > 0 ? (
        <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
          {check.links.map((entry, i) => (
            <ItemLinkView key={i} link={entry.link} testId="box-check-link">
              {entry.label}
            </ItemLinkView>
          ))}
        </p>
      ) : null}
    </li>
  );
}

const H = "text-xs font-semibold uppercase tracking-wider text-slate-400";

/** The design refactor (26 November 2026): one box of the map, opened. In the open: what it is and what its results
 * rest on, one line that counts its checks in their own words, and each place it uses cryptography with the checks of
 * that place (each a way to where the result lives). Then its fixes and what the files don't say about it. Behind one
 * fold, a Technical record: the lines of the files that name it, as data. It reads; it runs and decides nothing. */
export function BoxPanel({
  planId,
  boxKey,
  onClose,
}: {
  planId: number | null;
  boxKey: string | null;
  onClose: () => void;
}) {
  const [read, setRead] = useState<{ key: string; panel: ObservatoryPanel | null; error: string | null } | null>(null);
  useEffect(() => {
    if (boxKey === null || planId === null) return;
    let live = true;
    api
      .getObservatoryBox(planId, boxKey)
      .then((panel) => {
        if (live) setRead({ key: boxKey, panel, error: null });
      })
      .catch((e: unknown) => {
        if (live) setRead({ key: boxKey, panel: null, error: errorMessage(e) });
      });
    return () => {
      live = false;
    };
  }, [planId, boxKey]);
  const mine = read && read.key === boxKey ? read : null;
  const panel = mine?.panel ?? null;
  return (
    <DetailPanel
      open={boxKey !== null}
      item={boxKey}
      kicker={panel?.kind_label ?? "Observatory"}
      title={panel?.title ?? ""}
      subtitle={panel?.sub}
      onClose={onClose}
    >
      {mine?.error ? <ErrorBox>{mine.error}</ErrorBox> : null}
      {panel ? (
        <div data-testid="box-panel" data-box={panel.key} className="space-y-5 text-sm">
          <div className="space-y-2">
            {panel.part_of ? (
              <p data-testid="box-part-of" className="text-[13px] text-slate-400">
                Part of <span className="text-slate-200">{panel.part_of}</span>
              </p>
            ) : null}
            <WhereFromLine tag={panel.tag} />
            {panel.last ? (
              <p className="text-xs text-slate-400">
                {panel.last.label} <time dateTime={panel.last.at}>{formatTime(panel.last.at)}</time>
              </p>
            ) : null}
            <p data-testid="box-summary" className="break-words text-slate-200">
              {panel.summary}
            </p>
            {panel.note ? <p className="text-[13px] text-slate-400">{panel.note}</p> : null}
            {panel.ties.map((tie, i) => (
              <p key={i} className="text-[13px] text-slate-400">
                {tie.words}
              </p>
            ))}
          </div>

          {panel.spots.map((spot) => (
            <section key={spot.key} data-testid="box-spot" data-spot={spot.key} aria-label={spot.title}>
              <h3 className="flex flex-wrap items-baseline gap-x-2 text-sm font-semibold text-slate-100">
                {spot.title}
                <span className="text-xs font-normal text-slate-400">{spot.file_says}</span>
                {panel.tag ? null : <WhereFromTag tag={spot.tag} />}
              </h3>
              {spot.checks.length > 0 ? (
                <ul className="mt-2 rounded-lg border border-slate-800 px-3 py-2.5">
                  {spot.checks.map((check) => (
                    <Check key={check.id} check={check} tagged={panel.tag !== null || spot.tag !== null} />
                  ))}
                </ul>
              ) : spot.empty_text ? (
                <p className="mt-1 text-[13px] text-slate-500">{spot.empty_text}</p>
              ) : null}
            </section>
          ))}

          {panel.libraries.map((group) => (
            <section key={group.key} data-testid="box-libraries" aria-label={group.title}>
              <h3 className="text-sm font-semibold text-slate-100">{group.title}</h3>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-slate-400">
                {group.sub}
                <WhereFromTag tag={group.tag} />
              </p>
              <ul className="mt-2 space-y-1.5">
                {group.rows.map((row) => (
                  <li key={row.id} className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
                    <ItemLinkView link={row.link}>{row.label}</ItemLinkView>
                    <span className="text-xs text-slate-300">{row.answers_short}</span>
                  </li>
                ))}
              </ul>
              {group.more ? (
                <p className="mt-2 text-xs text-slate-400">
                  {group.more.label} <ItemLinkView link={group.more.link}>{group.more.link_label}</ItemLinkView>
                </p>
              ) : null}
            </section>
          ))}

          {panel.fixes.length > 0 ? (
            <section aria-label="Fixes" data-testid="box-fixes">
              <h3 className={H}>Fixes</h3>
              <ul className="mt-2 space-y-1.5">
                {panel.fixes.map((fix, i) => (
                  <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
                    <ItemLinkView link={fix.link} testId="box-fix">
                      {fix.label}
                    </ItemLinkView>
                    <span className="text-xs text-slate-400">{fix.sub}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {panel.gaps.items.length > 0 ? (
            <section aria-label={panel.gaps.title} data-testid="box-gaps">
              <h3 className={H}>{panel.gaps.title}</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[13px] text-slate-300 marker:text-slate-600">
                {panel.gaps.items.map((gap) => (
                  <li key={gap.key}>
                    {gap.text}{" "}
                    {gap.link ? <ItemLinkView link={gap.link}>{gap.link_label ?? "Open"}</ItemLinkView> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {panel.file_lines.some((f) => f.lines.length > 0) ? (
            <ProofFold kind="record" inside={panel.file_lines.map((f) => f.title)} testId="box-record">
              {panel.file_lines.map((file, i) => (
                <ProofPart
                  key={i}
                  n={i + 1}
                  title={file.title}
                  extra={<span className="font-mono text-xs font-normal text-slate-400">{file.filename}</span>}
                  testId="box-file-lines"
                >
                  <ul className="space-y-1.5">
                    {file.lines.map((line, j) => (
                      <li key={j} className="grid gap-x-3 gap-y-0.5 text-xs @md:grid-cols-[9rem_minmax(0,1fr)]">
                        <span className="font-mono text-slate-500">{line.where}</span>
                        <span className="min-w-0 break-all font-mono text-slate-300">{line.text}</span>
                      </li>
                    ))}
                  </ul>
                  {file.more > 0 ? (
                    <p className="mt-2 text-xs text-slate-500">
                      {file.more} more {file.more === 1 ? "line names" : "lines name"} it in this file.
                    </p>
                  ) : null}
                  <p className="mt-2 text-xs text-slate-500">Read from the file as data. Nothing in it is run.</p>
                </ProofPart>
              ))}
            </ProofFold>
          ) : null}

          <HistoryFold itemKey={panel.related_key} />
          <RelatedFold lines={panel.related} />
        </div>
      ) : boxKey !== null && !mine?.error ? (
        <p role="status" className="text-sm text-slate-400">
          Loading…
        </p>
      ) : null}
    </DetailPanel>
  );
}
