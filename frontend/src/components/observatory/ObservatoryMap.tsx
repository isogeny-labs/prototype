import { useRef } from "react";
import type {
  ObservatoryAlgorithm,
  ObservatoryBox,
  ObservatoryCheck,
  ObservatoryLibraries,
  ObservatorySpot,
  ObservatoryView,
} from "../../api";
import { ItemLinkView } from "../related";
import { DemoDataLabel, StatusChip, WhereFromTag } from "../ui";
import { MapLines } from "./MapLines";

/** One check of a spot, by name, with the word of its own page. It is a link to where that result lives. A check that
 * has not run says so and has no look. A retest's result, or the measurement after an Apply, stands beside the first
 * result and never in its place. */
export function CheckChip({ check, showTag }: { check: ObservatoryCheck; showTag: boolean }) {
  return (
    <span
      data-testid="map-check"
      data-check={check.id}
      data-kind={check.kind}
      // (a name and its word wrap inside their box; neither is ever drawn past its edge)
      className="inline-flex max-w-full min-w-0 flex-wrap items-center gap-1.5"
    >
      <ItemLinkView
        link={check.link}
        testId="map-check-link"
        className="inline-flex max-w-full min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 rounded-md py-0.5 text-xs text-slate-300 hover:text-sky-200"
      >
        <span className="min-w-0 break-words">{check.name}</span>{" "}
        {check.checked && check.tone ? (
          <StatusChip label={check.word} tone={check.tone} size="sm" wrap testId="map-check-word" />
        ) : (
          <span data-testid="map-check-word" className="text-slate-500">
            {check.running ? "Running" : check.word}
          </span>
        )}
      </ItemLinkView>
      {check.came_from ? <span className="text-[11px] text-slate-400">{check.came_from}</span> : null}
      {showTag ? <WhereFromTag tag={check.tag} /> : null}
      {check.beside.map((beside, i) => (
        <ItemLinkView
          key={i}
          link={beside.link}
          testId="map-check-beside"
          className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-sky-200"
        >
          <span>{beside.label}</span> <StatusChip label={beside.word} tone={beside.tone} size="sm" wrap />
        </ItemLinkView>
      ))}
    </span>
  );
}

/** One place cryptography sits in a box: its name, what the file says there, and its checks by name. */
function Spot({ spot, boxTagged }: { spot: ObservatorySpot; boxTagged: boolean }) {
  return (
    <li
      data-testid="map-spot"
      data-spot={spot.key}
      data-checked={spot.checked}
      className="border-t border-slate-800 pt-2 first:border-t-0 first:pt-0"
    >
      <p className="flex flex-wrap items-baseline gap-x-1.5 text-[13px]">
        <span className="font-medium text-slate-100">{spot.title}</span>
        <span data-testid="map-spot-file" className="text-xs text-slate-400">
          · {spot.file_says}
        </span>
        {!boxTagged ? <WhereFromTag tag={spot.tag} /> : null}
      </p>
      {spot.checks.length > 0 ? (
        <ul className="mt-1 flex min-w-0 flex-wrap gap-x-3 gap-y-1">
          {spot.checks.map((check) => (
            <li key={check.id}>
              <CheckChip check={check} showTag={!boxTagged && !spot.tag} />
            </li>
          ))}
        </ul>
      ) : spot.empty_text ? (
        <p className="mt-1 text-xs text-slate-500">{spot.empty_text}</p>
      ) : null}
    </li>
  );
}

function Box({ box, open, onOpen }: { box: ObservatoryBox; open: boolean; onOpen?: (key: string) => void }) {
  return (
    <article
      data-testid="map-box"
      data-node={box.key}
      data-kind={box.kind}
      data-observed={box.observed}
      aria-label={box.title}
      className={`relative min-w-0 rounded-xl border bg-slate-900 p-3.5 ${
        open
          ? "border-sky-400/70 shadow-[0_0_0_1px_var(--color-sky-400)]"
          : box.observed
            ? "border-slate-600"
            : "border-dashed border-slate-600"
      }`}
    >
      <header className="mb-2.5">
        <h4 className="text-sm font-semibold text-slate-50">
          {onOpen ? (
            <button
              type="button"
              data-testid="map-box-open"
              aria-expanded={open}
              onClick={() => onOpen(box.key)}
              className="text-left hover:text-sky-200"
            >
              {box.title}
            </button>
          ) : (
            box.title
          )}
        </h4>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
          <span>{box.sub}</span>
          <WhereFromTag tag={box.tag} testId="map-box-tag" />
        </p>
        {box.ties.map((tie, i) => (
          <p key={i} data-testid="map-box-tie" className="mt-1 text-xs text-slate-400">
            {tie.words}
          </p>
        ))}
        {box.note ? (
          <p data-testid="map-box-note" className="mt-1 text-xs text-slate-400">
            {box.note}
          </p>
        ) : null}
      </header>
      {box.spots.length > 0 ? (
        <ul className="space-y-2">
          {box.spots.map((spot) => (
            <Spot key={spot.key} spot={spot} boxTagged={box.tag !== null} />
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function Algorithm({ algorithm }: { algorithm: ObservatoryAlgorithm }) {
  return (
    <article
      data-testid="map-algorithm"
      data-node={algorithm.key}
      aria-label={algorithm.plain ?? algorithm.technical}
      className="min-w-0 rounded-xl border border-slate-700 bg-slate-900/70 p-3.5"
    >
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{algorithm.kind_label}</p>
      <h4 className="mt-0.5 text-sm font-semibold text-slate-50">{algorithm.plain ?? algorithm.technical}</h4>
      <p className="mt-0.5 text-xs text-slate-400">
        {algorithm.plain ? <span className="font-mono text-slate-300">{algorithm.technical}</span> : null}
        {algorithm.plain ? " · " : null}
        {algorithm.named}
      </p>
      <p data-testid="map-algorithm-used" className="mt-2 text-[13px] text-slate-300">
        {algorithm.used}
      </p>
    </article>
  );
}

function Libraries({ group }: { group: ObservatoryLibraries }) {
  return (
    <article
      data-testid="map-libraries"
      data-node={group.key}
      aria-label={group.title}
      className="min-w-0 rounded-xl border border-slate-700 bg-slate-900/70 p-3.5"
    >
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{group.kind_label}</p>
      <h4 className="mt-0.5 text-sm font-semibold text-slate-50">{group.title}</h4>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
        <span>{group.sub}</span>
        <WhereFromTag tag={group.tag} />
      </p>
      <ul className="mt-2 space-y-1.5">
        {group.rows.map((row) => (
          <li
            key={row.id}
            data-testid="map-library"
            className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]"
          >
            <ItemLinkView link={row.link} className="font-medium text-slate-100 hover:text-sky-200">
              {row.label}
            </ItemLinkView>
            <span className="flex flex-wrap items-center gap-1.5 text-xs text-slate-300">
              {row.answers_short}
              {group.tag ? null : <WhereFromTag tag={row.tag} />}
            </span>
          </li>
        ))}
      </ul>
      {group.more ? (
        <p className="mt-2 text-xs text-slate-400">
          {group.more.label}{" "}
          <ItemLinkView link={group.more.link} testId="map-libraries-more">
            {group.more.link_label}
          </ItemLinkView>
        </p>
      ) : null}
    </article>
  );
}

const LEGEND: Record<string, string> = {
  uses: "border-t-[1.5px] border-slate-500",
  live: "border-t-[1.5px] border-sky-400",
  ask: "border-t-[1.5px] border-dashed border-slate-500",
  unobserved: "h-3 rounded-sm border border-dashed border-slate-500",
};

/** The design refactor (26 November 2026): the map of the systems as the files describe them. Three rows: what is
 * outside (who connects, and this computer, which makes the handshakes), the service with the parts it is made of
 * (each with the places it uses cryptography and the checks of each place, by name, in the checks' own words), and
 * what they use (algorithms and libraries). The lines are the ones the files or a check give. The map repeats; it
 * decides nothing, scores nothing and starts nothing. */
export function ObservatoryMap({
  view,
  openBox = null,
  onOpenBox,
}: {
  view: ObservatoryView;
  openBox?: string | null;
  /** A box's name opens its panel. Without it the boxes are not buttons (the small map on the Overview). */
  onOpenBox?: (key: string) => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const stamp = JSON.stringify([
    view.lines,
    view.services.map((s) => s.boxes.map((b) => [b.key, b.spots.map((sp) => sp.checks.map((c) => c.word))])),
    view.libraries.map((l) => l.key),
    openBox,
  ]);
  const lower = view.algorithms.length + view.libraries.length + (view.libraries_note ? 1 : 0);
  return (
    // The map lays itself out by its own width, not the window's: beside an open box panel and the Otto panel it has a
    // third of the page, and then everything stands in one column.
    <div data-testid="observatory-map" className="@container min-w-0">
      <div ref={root} className="relative flex flex-col gap-y-14">
        <MapLines root={root} lines={view.lines} stamp={stamp} />
        {/* What is outside your systems. */}
        <div data-testid="map-lane" data-lane="outside" className="grid gap-4 @xl:grid-cols-2">
          {view.outside.map((o) => (
            <div
              key={o.key}
              data-testid="map-outside"
              data-node={o.key}
              className={`min-w-0 rounded-xl border bg-slate-950 px-3.5 py-2.5 ${
                o.key === "clients"
                  ? "border-dashed border-slate-600 @xl:mr-auto @xl:w-72"
                  : "border-slate-700 @xl:ml-auto @xl:w-72"
              }`}
            >
              <p className="text-sm font-semibold text-slate-100">{o.title}</p>
              <p className="mt-0.5 text-xs text-slate-400">{o.sub}</p>
            </div>
          ))}
        </div>

        {/* Your systems: each service with the parts it is made of. */}
        <div data-testid="map-lane" data-lane="systems" className="flex flex-col gap-6">
          {view.services.map((service) => (
            <section
              key={service.key}
              data-testid="map-service"
              data-node={service.key}
              aria-label={service.title ?? "Your systems"}
              className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4"
            >
              {/* (a line of the map is never drawn across a service's name: MapLines reads this mark and leads a line
                  that would cross it round by the side; a line that has to reach a part of the service from above
                  passes behind the name, which stands on the page's own colour above the lines) */}
              <header
                data-map-title
                className="relative -mx-1 mb-3 flex w-fit max-w-full flex-wrap items-baseline gap-x-2 gap-y-1 rounded bg-slate-950 px-1"
              >
                {service.title ? <h3 className="text-[15px] font-semibold text-slate-50">{service.title}</h3> : null}
                {service.version ? <span className="font-mono text-xs text-slate-400">{service.version}</span> : null}
                {service.is_demo ? <DemoDataLabel /> : null}
                <span data-testid="map-service-sub" className="text-xs text-slate-400">
                  {service.sub}
                </span>
              </header>
              <div className="grid gap-4 @2xl:grid-cols-2">
                {service.boxes.map((box) => (
                  <Box key={box.key} box={box} open={box.key === openBox} onOpen={onOpenBox} />
                ))}
              </div>
            </section>
          ))}
        </div>

        {/* What they use. */}
        {lower > 0 ? (
          <div data-testid="map-lane" data-lane="uses" className="grid gap-4 @2xl:grid-cols-2">
            {view.algorithms.map((algorithm) => (
              <Algorithm key={algorithm.key} algorithm={algorithm} />
            ))}
            {view.libraries.map((group) => (
              <Libraries key={group.key} group={group} />
            ))}
            {view.libraries_note ? (
              <article
                data-testid="map-libraries-note"
                className="min-w-0 rounded-xl border border-dashed border-slate-600 bg-slate-950 p-3.5"
              >
                <h4 className="text-sm font-semibold text-slate-200">{view.libraries_note.title}</h4>
                <p className="mt-0.5 text-xs text-slate-400">{view.libraries_note.sub}</p>
                <p className="mt-2 text-[13px] text-slate-300">
                  {view.libraries_note.text} <ItemLinkView link={view.libraries_note.link}>Dependencies</ItemLinkView>
                </p>
              </article>
            ) : null}
          </div>
        ) : null}
      </div>

      <ul
        data-testid="map-legend"
        aria-label="What the lines mean"
        className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-400"
      >
        {view.legend.map((item) => (
          <li key={item.kind} data-kind={item.kind} className="flex items-center gap-2">
            <span aria-hidden="true" className={`inline-block w-6 ${LEGEND[item.kind] ?? ""}`} />
            {item.text}
          </li>
        ))}
        <li className="text-slate-500">{view.legend_note}</li>
      </ul>
    </div>
  );
}
