import { useContext, useEffect, useState } from "react";
import { api, errorMessage, type ObservatoryView } from "../../api";
import { usePanelStamp } from "../../changes";
import { ItemPageContext, PageHeader, TableWithPanel } from "../layout";
import { ItemLinkView } from "../related";
import { ErrorBox, RichTextView, WhereFromTag } from "../ui";
import { BoxPanel } from "./BoxPanel";
import { CheckChip, ObservatoryMap } from "./ObservatoryMap";

const POLL_MS = 1000;

/** The same boxes, places and checks as a table: for a screen reader, for printing, and for an estate too big to draw. */
function ObservatoryList({ view, onOpenBox }: { view: ObservatoryView; onOpenBox?: (key: string) => void }) {
  const boxes = view.services.flatMap((service) => service.boxes.map((box) => ({ service, box })));
  return (
    <div data-testid="observatory-list" className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/30">
      <table aria-label="Your systems, as a list" className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-xs font-medium uppercase tracking-wider text-slate-500">
            <th scope="col" className="px-4 py-2.5 font-medium">
              System
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Where the cryptography is
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              What the checks found
            </th>
          </tr>
        </thead>
        <tbody>
          {boxes.flatMap(({ service, box }) =>
            (box.spots.length > 0 ? box.spots : [null]).map((spot, i) => (
              <tr
                key={`${box.key}/${spot?.key ?? "none"}`}
                data-testid="list-row"
                data-box={box.key}
                className="border-b border-slate-800/70 last:border-b-0"
              >
                {i === 0 ? (
                  <th
                    scope="rowgroup"
                    rowSpan={Math.max(box.spots.length, 1)}
                    className="px-4 py-3 align-top font-normal"
                  >
                    {onOpenBox ? (
                      <button
                        type="button"
                        onClick={() => onOpenBox(box.key)}
                        className="text-left font-medium text-slate-100 hover:text-sky-200"
                      >
                        {box.title}
                      </button>
                    ) : (
                      <span className="font-medium text-slate-100">{box.title}</span>
                    )}
                    <span className="mt-0.5 block text-xs text-slate-400">{box.sub}</span>
                    {service.title ? (
                      <span data-testid="list-service" className="block text-xs text-slate-500">
                        In {service.title}
                        {service.version ? ` ${service.version}` : ""}. {service.sub}
                      </span>
                    ) : null}
                    <span className="mt-1 block">
                      <WhereFromTag tag={box.tag} />
                    </span>
                    {box.ties.map((tie, t) => (
                      <span key={t} data-testid="list-tie" className="mt-1 block text-xs text-slate-400">
                        {tie.words}
                      </span>
                    ))}
                    {box.note ? <span className="mt-1 block text-xs text-slate-400">{box.note}</span> : null}
                  </th>
                ) : null}
                <td className="px-4 py-3 align-top">
                  {spot ? (
                    <>
                      <span className="block font-medium text-slate-200">{spot.title}</span>
                      <span className="block text-xs text-slate-400">{spot.file_says}</span>
                    </>
                  ) : (
                    // (a part with no place of its own on the map: the map's own note about it stands in the first
                    // column; nothing is said here that the read does not say)
                    <span aria-hidden="true" className="text-xs text-slate-600">
                      –
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 align-top">
                  {spot && spot.checks.length > 0 ? (
                    <ul className="flex flex-col gap-1">
                      {spot.checks.map((check) => (
                        <li key={check.id}>
                          <CheckChip check={check} showTag={box.tag === null} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-xs text-slate-500">{spot?.empty_text ?? ""}</span>
                  )}
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
      {/* The libraries of the dependency list, as the map groups them (or the map's own line that none was added). */}
      {view.libraries.length > 0 ? (
        <table
          aria-label="Libraries, as a list"
          data-testid="list-libraries"
          className="w-full border-collapse border-t border-slate-800 text-left text-sm"
        >
          <thead>
            <tr className="border-b border-slate-800 text-xs font-medium uppercase tracking-wider text-slate-500">
              <th scope="col" className="px-4 py-2.5 font-medium">
                Libraries of
              </th>
              <th scope="col" className="px-4 py-2.5 font-medium">
                Library
              </th>
              <th scope="col" className="px-4 py-2.5 font-medium">
                Post-quantum answers
              </th>
            </tr>
          </thead>
          <tbody>
            {view.libraries.flatMap((group) =>
              group.rows.map((row, i) => (
                <tr
                  key={`${group.key}/${row.id}`}
                  data-testid="list-library"
                  className="border-b border-slate-800/70 last:border-b-0"
                >
                  {i === 0 ? (
                    <th scope="rowgroup" rowSpan={group.rows.length} className="px-4 py-3 align-top font-normal">
                      <span className="font-medium text-slate-100">{group.title}</span>
                      <span className="mt-0.5 block text-xs text-slate-400">{group.sub}</span>
                      {group.more ? (
                        <span className="mt-1 block text-xs text-slate-400">
                          {group.more.label} <ItemLinkView link={group.more.link}>{group.more.link_label}</ItemLinkView>
                        </span>
                      ) : null}
                    </th>
                  ) : null}
                  <td className="px-4 py-3 align-top">
                    <ItemLinkView link={row.link}>{row.label}</ItemLinkView>
                    <span className="block text-xs text-slate-400">{row.via_words}</span>
                  </td>
                  <td className="px-4 py-3 align-top text-slate-200">
                    {row.answers_short} <WhereFromTag tag={row.tag} />
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      ) : view.libraries_note ? (
        <p data-testid="list-libraries-note" className="border-t border-slate-800 px-4 py-3 text-[13px] text-slate-300">
          <span className="font-medium text-slate-200">{view.libraries_note.title}:</span> {view.libraries_note.sub}.{" "}
          {view.libraries_note.text} <ItemLinkView link={view.libraries_note.link}>Dependencies</ItemLinkView>
        </p>
      ) : null}
      {view.lines.length > 0 ? (
        <div className="border-t border-slate-800 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">The lines of the map, in words</p>
          <ul data-testid="list-lines" className="mt-1.5 space-y-1 text-[13px] text-slate-300">
            {view.algorithms.map((a) => (
              <li key={a.key}>
                <span className="font-medium text-slate-200">{a.plain ?? a.technical}</span>
                {a.plain ? <span className="font-mono text-xs text-slate-400"> {a.technical}</span> : null}. {a.used}
              </li>
            ))}
            {view.lines
              // (a line to an algorithm is said by the algorithm's own sentence above; every other line is said here)
              .filter((line) => !view.algorithms.some((a) => a.key === line.end || a.key === line.start))
              .map((line, i) => (
                <li key={i} data-kind={line.kind}>
                  {view.legend.find((l) => l.kind === line.kind)?.text}: {nameOf(view, line.start)} to{" "}
                  {nameOf(view, line.end)}
                  {line.label && line.label !== "?" ? ` (${line.label})` : ""}.
                </li>
              ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function nameOf(view: ObservatoryView, key: string): string {
  const outside = view.outside.find((o) => o.key === key);
  if (outside) return outside.title;
  for (const service of view.services) {
    if (service.key === key) return service.title ?? "your systems";
    const box = service.boxes.find((b) => b.key === key);
    if (box) return box.title;
  }
  return (
    view.algorithms.find((a) => a.key === key)?.technical ?? view.libraries.find((l) => l.key === key)?.title ?? key
  );
}

/** The design refactor (26 November 2026): the Observatory, the first page of step 2 (Observe). It draws the systems
 * the files describe as a map, marks where each uses cryptography, and puts every check where it belongs, in the
 * check's own words. The four counts on top are the Overview's own. Under the map: what the files don't say, each
 * with where it can be filled in. A box opens its panel. Looking at the page runs nothing: every check is still
 * started where it always was. It is no result and no score. */
export function ObservatoryPage({
  assessmentId,
  openItem = null,
}: {
  assessmentId: number;
  /** A box (its key) or an item of another page (the key of its Related block) to show on the map. */
  openItem?: string | null;
}) {
  const [view, setView] = useState<ObservatoryView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"map" | "list">("map");
  const [openBox, setOpenBox] = useState<string | null>(null);
  const [placed, setPlaced] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const panelStamp = usePanelStamp();
  const asPage = Boolean(useContext(ItemPageContext)?.asPage);

  useEffect(() => {
    let live = true;
    api
      .getObservatory(assessmentId)
      .then((next) => {
        if (!live) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [assessmentId, tick, panelStamp]);

  const busy = view?.busy === true;
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [busy, view]);

  // The item the address names: a box of the map opens; an item of another page ("Show on the map" in a result's
  // panel) is looked up once, and the box it sits in opens.
  const planId = view?.plan_id ?? null;
  const isBox =
    view !== null && openItem !== null && view.services.some((s) => s.boxes.some((b) => b.key === openItem));
  if (view !== null && openItem !== null && isBox && placed !== openItem) {
    // (told while drawing, as the other pages do for the item their address names: no second drawing is needed)
    setPlaced(openItem);
    setOpenBox(openItem);
  }
  const lookUp =
    view !== null && openItem !== null && !isBox && placed !== openItem && planId !== null ? openItem : null;
  useEffect(() => {
    if (lookUp === null || planId === null) return;
    let live = true;
    api
      .getObservatoryPlace(planId, lookUp)
      .then((found) => {
        if (!live) return;
        setPlaced(lookUp);
        if (found.place?.box) setOpenBox(found.place.box);
      })
      .catch(() => {
        if (live) setPlaced(lookUp);
      });
    return () => {
      live = false;
    };
  }, [lookUp, planId]);

  if (!view) {
    return error ? (
      <ErrorBox title="The Observatory couldn't be loaded">{error}</ErrorBox>
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  }

  const openOne =
    planId !== null ? (key: string) => setOpenBox((cur) => (cur === key && !asPage ? null : key)) : undefined;

  return (
    <section aria-label={view.title} data-testid="observatory-page" data-state={view.state}>
      <PageHeader
        title={view.title}
        description={<span data-testid="observatory-subline">{view.subline}</span>}
        actions={
          view.state === "empty" ? undefined : (
            <div
              role="group"
              aria-label="Observatory view"
              data-testid="observatory-views"
              className="inline-flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1"
            >
              {(
                [
                  ["map", "Map"],
                  ["list", "List"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={mode === key}
                  onClick={() => setMode(key)}
                  className={`rounded-md px-3 py-1 text-[13px] font-medium transition-colors ${
                    mode === key ? "bg-slate-800 text-slate-50" : "text-slate-400 hover:text-slate-100"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )
        }
      />
      {error ? (
        <div className="mb-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      {view.state === "empty" && view.empty ? (
        <p
          data-testid="observatory-empty"
          className="rounded-xl border border-slate-800 px-4 py-8 text-center text-sm text-slate-300"
        >
          {view.empty.text}{" "}
          <ItemLinkView link={view.empty.link} testId="observatory-empty-link">
            {view.empty.link_label}
          </ItemLinkView>
        </p>
      ) : (
        <>
          {view.banner ? (
            <p
              data-testid="observatory-banner"
              className="mb-4 rounded-lg border border-sky-400/30 bg-sky-400/[0.06] px-4 py-3 text-sm text-slate-200"
            >
              <strong className="font-semibold text-slate-50">{view.banner.strong}</strong> {view.banner.text}{" "}
              <ItemLinkView link={view.banner.link} testId="observatory-banner-link">
                {view.banner.link_label}
              </ItemLinkView>
            </p>
          ) : null}

          {/* Every check of the assessment by what its result rests on: the Overview's own four counts. */}
          <ul
            aria-label="Where it came from"
            data-testid="observatory-counts"
            className="mb-2 grid grid-cols-2 gap-3 lg:grid-cols-4"
          >
            {view.counts.map((count) => (
              <li
                key={count.key}
                data-testid="observatory-count"
                data-source={count.key}
                data-count={count.count}
                title={count.meaning}
                className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3"
              >
                <WhereFromTag tag={{ key: count.key, label: count.label, meaning: count.meaning, note: null }} />
                <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-slate-50">{count.count}</p>
                <p className="mt-0.5 text-xs text-slate-500">{count.line}</p>
              </li>
            ))}
          </ul>
          <p data-testid="observatory-counts-note" className="mb-5 text-xs text-slate-500">
            {view.counts_note}
          </p>

          <TableWithPanel
            panelOpen={openBox !== null}
            table={
              <section
                aria-label={view.map_title}
                className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/40 p-4"
              >
                <header className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h2 className="text-sm font-semibold text-slate-100">{view.map_title}</h2>
                  <p data-testid="observatory-built-from" className="text-xs text-slate-400">
                    <RichTextView parts={view.built_from} />
                  </p>
                </header>
                {view.structure_note ? (
                  <p data-testid="observatory-structure-note" className="mb-3 text-[13px] text-slate-400">
                    {view.structure_note}
                  </p>
                ) : null}
                {mode === "map" ? (
                  <ObservatoryMap view={view} openBox={openBox} onOpenBox={openOne} />
                ) : (
                  <ObservatoryList view={view} onOpenBox={openOne} />
                )}
                {view.not_drawn ? (
                  <p data-testid="observatory-not-drawn" className="mt-3 text-[13px] text-slate-400">
                    {view.not_drawn}
                  </p>
                ) : null}
              </section>
            }
            panel={<BoxPanel planId={planId} boxKey={openBox} onClose={() => setOpenBox(null)} />}
          />

          <section
            aria-label={view.gaps.title}
            data-testid="observatory-gaps"
            className="mt-6 rounded-xl border border-slate-800 bg-slate-900/40 p-4"
          >
            <h2 className="text-sm font-semibold text-slate-100">{view.gaps.title}</h2>
            <p className="mt-0.5 text-xs text-slate-400">{view.gaps.note}</p>
            <ul className="mt-2.5 list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-slate-300 marker:text-slate-600">
              {view.gaps.items.map((gap) => (
                <li key={gap.key} data-testid="observatory-gap" data-gap={gap.key}>
                  {gap.text}{" "}
                  {gap.link ? (
                    <ItemLinkView link={gap.link} testId="observatory-gap-link">
                      {gap.link_label ?? "Open"}
                    </ItemLinkView>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}
