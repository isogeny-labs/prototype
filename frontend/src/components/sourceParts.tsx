import type { Source as WhereFrom } from "../api";
import type { TablePart } from "./layout";
import { WhereFromTag } from "./ui";

/** The design refactor (26 November 2026): a list of results or fixes is drawn in parts, by what each row rests on.
 * The part's heading says it once: its name, the row's own tag, and the tag's own line on what it means (the
 * backend's words). A row with no tag (nothing was observed or proven for it) sits in a last part with no tag at its
 * head. The parts are headings, not filters, and they decide nothing: every row is still on the page. */
export const SOURCE_PARTS: { key: WhereFrom["key"] | "none"; title: string }[] = [
  { key: "live", title: "On your systems" },
  { key: "lab", title: "On copies on this computer" },
  { key: "published", title: "Said by the maker" },
  { key: "file", title: "Only in your file" },
  { key: "none", title: "No result yet" },
];

export function sourceParts<T>(rows: T[], tagOf: (row: T) => WhereFrom | null | undefined): TablePart<T>[] {
  const keyOf = (row: T) => tagOf(row)?.key ?? "none";
  // The parts come in the order the rows do (the first row's part first), so a list still opens on the row it always
  // opened on; the rows with no result yet come last.
  const seen = Array.from(new Set(rows.map(keyOf)));
  const order = [...seen.filter((key) => key !== "none"), ...seen.filter((key) => key === "none")];
  return order.map((key) => {
    const part = SOURCE_PARTS.find((p) => p.key === key)!;
    const mine = rows.filter((row) => keyOf(row) === part.key);
    const tag = mine.map(tagOf).find((t) => t) ?? null;
    return {
      key: part.key,
      rows: mine,
      head: (
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span data-testid="table-part-title" className="text-[13px] font-semibold text-slate-200">
            {part.title}
          </span>
          <span data-testid="table-part-count" className="tabular-nums text-slate-500">
            {mine.length}
          </span>
          {tag ? (
            <>
              <WhereFromTag tag={tag} testId="table-part-tag" />
              <span data-testid="table-part-meaning" className="min-w-0 text-slate-400">
                {tag.meaning}
              </span>
            </>
          ) : null}
        </span>
      ),
    };
  });
}
