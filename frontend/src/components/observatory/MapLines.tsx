import { useEffect, useRef, useState, type RefObject } from "react";
import type { ObservatoryLine } from "../../api";

interface Drawn {
  key: string;
  kind: ObservatoryLine["kind"];
  path: string;
  label: string;
  x: number;
  y: number;
}

const escape = (value: string) =>
  typeof CSS !== "undefined" && typeof CSS.escape === "function" ? CSS.escape(value) : value.replace(/["\\]/g, "\\$&");

/** Where each line runs, measured from the boxes as the browser laid them out: from the lower edge of the upper box
 * to the upper edge of the lower one, or straight across between two boxes side by side. */
function measure(root: HTMLElement, lines: ObservatoryLine[]): { drawn: Drawn[]; width: number; height: number } {
  const frame = root.getBoundingClientRect();
  const boxOf = (key: string) => {
    const node = root.querySelector<HTMLElement>(`[data-node="${escape(key)}"]`);
    if (!node) return null;
    const r = node.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return null;
    return {
      left: r.left - frame.left,
      top: r.top - frame.top,
      right: r.right - frame.left,
      bottom: r.bottom - frame.top,
      // (a part drawn inside a service's frame: a label is kept out of that frame, off the service's own title)
      inside:
        node.getAttribute("data-testid") !== "map-service" && node.closest('[data-testid="map-service"]') !== null,
    };
  };
  // What a line must not be drawn across: every other box of the map, and a service's own name.
  const blocks = Array.from(root.querySelectorAll<HTMLElement>("[data-node], [data-map-title]"))
    .filter((node) => node.getAttribute("data-testid") !== "map-service")
    .map((node) => {
      const r = node.getBoundingClientRect();
      return {
        key: node.getAttribute("data-node"),
        left: r.left - frame.left,
        top: r.top - frame.top,
        right: r.right - frame.left,
        bottom: r.bottom - frame.top,
      };
    });
  let aside = 0; // (how many lines were led round by the side so far: each gets a track of its own)
  // Lines that end on the same box are spread along its edge, so they do not run into one arrow.
  const endsAt = new Map<string, number>();
  const taken = new Map<string, number>();
  for (const line of lines) endsAt.set(line.end, (endsAt.get(line.end) ?? 0) + 1);
  const drawn: Drawn[] = [];
  lines.forEach((line, i) => {
    const a = boxOf(line.start);
    const b = boxOf(line.end);
    if (!a || !b) return;
    const share = endsAt.get(line.end) ?? 1;
    const nth = taken.get(line.end) ?? 0;
    taken.set(line.end, nth + 1);
    const along = (nth + 1) / (share + 1);
    const ax = (a.left + a.right) / 2;
    const bx = b.left + (b.right - b.left) * along;
    let path: string;
    let x: number;
    let y: number;
    // A label stands in the free room between the rows, next to the end of its line that is outside a service's frame
    // (a line ties a part inside a service to something outside it, or two things outside).
    const NEAR = 18;
    // Two boxes one under the other with something between them (the map in one column, beside two open panels): a
    // straight line would run across what stands between, so the line is led round by the side of the column.
    const [upper, lower] = a.bottom <= b.top ? [a, b] : [b, a];
    const shared = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const stacked = upper.bottom <= lower.top && shared > 0.5 * Math.min(a.right - a.left, b.right - b.left);
    const across =
      stacked &&
      blocks.some(
        (o) =>
          o.key !== line.start &&
          o.key !== line.end &&
          o.top < lower.top &&
          o.bottom > upper.bottom &&
          o.left < Math.max(ax, bx) + 2 &&
          o.right > Math.min(ax, bx) - 2,
      );
    if (across) {
      const track = 7 + 5 * Math.floor(aside / 2);
      const right = aside % 2 === 0;
      aside += 1;
      const edge = right ? Math.max(a.right, b.right) + track : Math.min(a.left, b.left) - track;
      const gx = Math.min(Math.max(edge, 2), frame.width - 2);
      const ay = Math.min(a.top + 22, (a.top + a.bottom) / 2);
      const by = Math.min(b.top + 22, (b.top + b.bottom) / 2);
      path = `M ${right ? a.right : a.left} ${ay} L ${gx} ${ay} L ${gx} ${by} L ${right ? b.right : b.left} ${by}`;
      // (its label stands in the free room just above the lower box, or just under the upper one)
      [x, y] =
        a.inside && !b.inside
          ? [bx, b === lower ? b.top - NEAR : b.bottom + NEAR]
          : [ax, a === upper ? a.bottom + NEAR : a.top - NEAR];
    } else if (a.bottom <= b.top) {
      const mid = (a.bottom + b.top) / 2;
      path = `M ${ax} ${a.bottom} C ${ax} ${mid}, ${bx} ${mid}, ${bx} ${b.top}`;
      [x, y] = [(ax + bx) / 2, mid];
      if (a.inside && !b.inside) [x, y] = [bx, b.top - NEAR];
      else if (!a.inside && b.inside) [x, y] = [ax, a.bottom + NEAR];
    } else if (b.bottom <= a.top) {
      const mid = (b.bottom + a.top) / 2;
      path = `M ${ax} ${a.top} C ${ax} ${mid}, ${bx} ${mid}, ${bx} ${b.bottom}`;
      [x, y] = [(ax + bx) / 2, mid];
      if (a.inside && !b.inside) [x, y] = [bx, b.bottom + NEAR];
      else if (!a.inside && b.inside) [x, y] = [ax, a.top - NEAR];
    } else {
      const ay = (a.top + a.bottom) / 2;
      const by = (b.top + b.bottom) / 2;
      const [from, to] = a.right <= b.left ? [a.right, b.left] : [a.left, b.right];
      path = `M ${from} ${ay} L ${to} ${by}`;
      [x, y] = [(from + to) / 2, (ay + by) / 2];
    }
    drawn.push({
      key: `${line.start}>${line.end}>${i}`,
      kind: line.kind,
      path,
      label: line.label,
      // (kept inside the map's frame, whatever its width)
      x: Math.min(Math.max(x, 80), Math.max(frame.width - 80, 80)),
      y,
    });
  });
  return { drawn, width: frame.width, height: frame.height };
}

const LOOK: Record<ObservatoryLine["kind"], { stroke: string; dash?: string; marker?: string; text: string }> = {
  // the files say one uses the other
  uses: { stroke: "var(--color-slate-500)", text: "text-slate-300" },
  // a connection the app made from this computer
  live: { stroke: "var(--color-sky-400)", marker: "url(#observatory-arrow)", text: "text-sky-200" },
  // the files don't say
  ask: { stroke: "var(--color-slate-600)", dash: "4 4", text: "text-slate-400" },
};

/** The lines of the map, drawn over it. Each comes from the files or from a check, and the read behind the page says
 * which (`kind`); this only draws them where the boxes are. They are a picture for the eye: the same facts are said
 * in words under the map and in the List view, so the picture is hidden from a screen reader. */
export function MapLines({
  root,
  lines,
  stamp,
}: {
  root: RefObject<HTMLElement | null>;
  lines: ObservatoryLine[];
  /** Changes when the map's content does, so the lines are measured again. */
  stamp: string;
}) {
  const [shape, setShape] = useState<{ drawn: Drawn[]; width: number; height: number } | null>(null);
  // (`stamp` says when the lines change; the newest lines are read at the moment they are measured)
  const latest = useRef(lines);
  useEffect(() => {
    latest.current = lines;
  });
  // (after the page is drawn, not during: the map's own element is attached only once its children are in place)
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const again = () => setShape(measure(node, latest.current));
    again();
    if (typeof ResizeObserver === "undefined") return;
    const watcher = new ResizeObserver(again);
    watcher.observe(node);
    return () => watcher.disconnect();
    // (`stamp` stands for the lines and the boxes)
  }, [root, stamp]);
  if (!shape || shape.drawn.length === 0) return null;
  return (
    <div aria-hidden="true" data-testid="map-lines" className="pointer-events-none absolute inset-0">
      <svg width={shape.width} height={shape.height} className="absolute inset-0 overflow-visible">
        <defs>
          <marker
            id="observatory-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto"
          >
            <path d="M0 0L10 5L0 10z" fill="var(--color-sky-400)" />
          </marker>
        </defs>
        {shape.drawn.map((line) => (
          <path
            key={line.key}
            data-kind={line.kind}
            d={line.path}
            fill="none"
            stroke={LOOK[line.kind].stroke}
            strokeWidth={1.5}
            strokeDasharray={LOOK[line.kind].dash}
            markerEnd={LOOK[line.kind].marker}
          />
        ))}
      </svg>
      {shape.drawn.map((line) => (
        <span
          key={line.key}
          data-testid="map-line-label"
          style={{ left: line.x, top: line.y }}
          title={line.label}
          className={`absolute max-w-40 -translate-x-1/2 -translate-y-1/2 truncate rounded-full border border-slate-800 bg-slate-950 px-2 py-0.5 text-[11px] ${LOOK[line.kind].text}`}
        >
          {line.label}
        </span>
      ))}
    </div>
  );
}
