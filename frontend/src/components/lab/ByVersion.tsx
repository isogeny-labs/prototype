import type { CheckGroup, CheckRow } from "../../api";
import { ItemLinkView } from "../related";
import { ResultBadge, StatusView, WhereFromTag } from "../ui";

/** One cell: the check's own result on that version, as the reviewer worded it, with its mark where it has one. */
function Cell({ row }: { row: CheckRow | undefined }) {
  if (!row)
    return (
      <span data-testid="version-cell" data-state="none" className="text-xs text-slate-500">
        Not run on this version
      </span>
    );
  return (
    <span data-testid="version-cell" data-check={row.id} className="flex flex-col items-start gap-1">
      {row.status ? (
        <StatusView status={row.status} />
      ) : row.result ? (
        <span className="flex flex-wrap items-center gap-1.5">
          <ResultBadge label={row.result.label} tone={row.result.tone} wrap />
          <WhereFromTag tag={row.source_tag} />
        </span>
      ) : (
        <span className="text-xs text-slate-500">Not run yet</span>
      )}
      {row.mark ? (
        // (a server test that ran again on an unchanged server says so)
        <span data-testid="version-mark" className="text-xs text-slate-400">
          {row.mark}
        </span>
      ) : null}
      {row.evidence_link ? (
        <ItemLinkView link={row.evidence_link} testId="version-open" className="text-xs text-sky-300 hover:underline">
          Open
        </ItemLinkView>
      ) : null}
    </span>
  );
}

/** The design refactor (26 November 2026): Results, By version. Every test of the plan on every version it ran on,
 * side by side: the first runs, then one column for each version a retest ran on, oldest first. It is drawn from the
 * same rows Checks lists under "Retests by version"; it words no result and decides none. */
export function ByVersion({ group }: { group: CheckGroup }) {
  const parts = group.parts;
  const tests = group.rows.filter((r) => r.id.startsWith("test-"));
  // (the blocks come newest first; a table reads oldest first, left to right)
  const versions = [...(parts?.retests.blocks ?? [])].reverse();
  const cellOf = (rows: CheckRow[], test: CheckRow) => rows.find((r) => r.link.item === test.id);
  return (
    <div data-testid="by-version" className="min-w-0">
      {versions.length === 0 ? (
        <p data-testid="by-version-empty" className="mb-3 text-sm text-slate-400">
          {parts?.retests.empty_text ?? "No retest has run yet, so there is one version to show."}
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/30">
        <table aria-label="Results by version" className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 align-bottom text-xs text-slate-400">
              <th scope="col" className="px-4 py-2.5 font-medium uppercase tracking-wider text-slate-500">
                Test
              </th>
              <th
                scope="col"
                data-testid="version-column"
                data-version="first"
                className="min-w-[10rem] px-4 py-2.5 font-medium"
              >
                <span className="block uppercase tracking-wider text-slate-500">First run</span>
                {parts?.plan.note ? (
                  <span className="mt-0.5 block font-normal normal-case text-slate-400">{parts.plan.note}</span>
                ) : null}
              </th>
              {versions.map((block) => (
                <th
                  key={block.key}
                  scope="col"
                  data-testid="version-column"
                  data-version={block.key}
                  className="min-w-[10rem] px-4 py-2.5 font-medium"
                >
                  <span className="block font-semibold text-slate-200">{block.title}</span>
                  <span className="mt-0.5 block font-normal text-slate-400">{block.line}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tests.map((test) => (
              <tr
                key={test.id}
                data-testid="version-row"
                data-check={test.id}
                className="border-b border-slate-800/70 last:border-b-0"
              >
                <th scope="row" className="px-4 py-3 align-top font-normal">
                  <span className="block font-medium text-slate-100">{test.name}</span>
                  <span className="block text-xs text-slate-400">{test.ran_on}</span>
                </th>
                <td className="px-4 py-3 align-top">
                  <Cell row={test} />
                </td>
                {versions.map((block) => (
                  <td key={block.key} className="px-4 py-3 align-top">
                    <Cell row={cellOf(block.rows, test)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
