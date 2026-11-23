import type { LibraryEvidenceRow } from "../../api";
import { AlgoName } from "../plainName";
import { DataTable, DetailPanel, type Column } from "../layout";
import { ItemLinkView, RelatedFor } from "../related";
import { NameText, ProofChip, ResultBadge, SourceTag, WhereFromTag } from "../ui";

function Blocks({ library }: { library: LibraryEvidenceRow }) {
  if (library.blocks.length === 0) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {library.blocks.map((b) => (
        <ItemLinkView
          key={`${b.system}/${b.track}`}
          link={{ page: "migration/roadmap", item: b.system_key ?? null }}
          testId="blocks-marker"
          className="rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-100 hover:underline"
        >
          {b.words}
        </ItemLinkView>
      ))}
    </span>
  );
}

const columns: Column<LibraryEvidenceRow>[] = [
  {
    key: "library",
    header: "Library",
    minWidth: 160,
    render: (l) => (
      <>
        <NameText text={l.name} className="block font-medium text-slate-100" />
        <span className="block text-xs text-slate-400">{l.via_words}</span>
        <Blocks library={l} />
      </>
    ),
  },
  {
    key: "answers",
    header: "Answers",
    minWidth: 150,
    render: (l) => (
      // (22 November 2026: where its answers came from, taken together)
      <span className="flex flex-col items-start gap-1">
        <span className="text-sm text-slate-200">{l.answers_short}</span>
        <WhereFromTag tag={l.source_tag} />
      </span>
    ),
  },
];
// Beside an open panel: the same two columns, narrower, so they fit the room left at 1440 pixels wide.
const compactColumns: Column<LibraryEvidenceRow>[] = [
  { ...columns[0]!, minWidth: 120 },
  { ...columns[1]!, minWidth: 96 },
];

/** Phase 5b: Evidence's Dependencies group: one row per library of the list, with its answers as Dependencies words them. */
export function LibraryTable({
  libraries,
  selectedId,
  onOpen,
}: {
  libraries: LibraryEvidenceRow[];
  selectedId: string | null;
  onOpen: (id: string) => void;
}) {
  return (
    <DataTable
      label="Libraries"
      columns={columns}
      compactColumns={compactColumns}
      rows={libraries}
      rowKey={(l) => l.id}
      rowTestId="library-row"
      selectedKey={selectedId}
      onRowClick={(l) => onOpen(l.id)}
    />
  );
}

/** One library in the panel: its answers with their labels and reasons, each lookup's source, the Blocks marker, and
 * Open in Dependencies (where its measurement and its Details and evidence are). */
export function LibraryPanel({ library, onClose }: { library: LibraryEvidenceRow | null; onClose: () => void }) {
  return (
    <DetailPanel
      open={library !== null}
      item={library?.id ?? null}
      title={library?.name ?? ""}
      subtitle={library?.via_words}
      onClose={onClose}
    >
      {library ? (
        <div data-testid="library-panel" className="space-y-4 text-sm">
          <Blocks library={library} />
          <ul className="space-y-3">
            {(library.cells ?? []).map((c) => (
              <li key={c.question} className="rounded-lg border border-slate-800 p-3">
                <p className="text-xs text-slate-400">
                  <AlgoName
                    text={
                      c.question === "ml_kem_768"
                        ? "ML-KEM-768"
                        : c.question === "x25519mlkem768"
                          ? "X25519MLKEM768"
                          : "ML-DSA-65"
                    }
                  />
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <ResultBadge label={c.answer_words} tone={c.tone} />
                  <WhereFromTag tag={c.source_tag} />
                  {c.label_words ? <ProofChip source={c.source_tag?.key ?? null}>{c.label_words}</ProofChip> : null}
                </div>
                {c.no_reason ? (
                  <p className="mt-1 text-slate-200">{c.no_reason}</p>
                ) : (
                  <p className="mt-1 text-slate-400">{c.reason}</p>
                )}
              </li>
            ))}
          </ul>
          {(library.lookups ?? []).filter((l) => !l.repeat).length > 0 ? (
            <section aria-label="Sources" className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Sources</h3>
              {(library.lookups ?? [])
                .filter((l) => !l.repeat)
                .map((l, i) => (
                  <div key={i} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                    <p className="text-slate-100">
                      {l.title} <SourceTag source="published">Release notes say</SourceTag>
                    </p>
                    <blockquote className="mt-1 border-l-2 border-slate-700 pl-2 text-slate-300">
                      “{l.quote}”
                    </blockquote>
                    <p className="mt-1 text-xs text-slate-400">
                      checked {l.checked} ·{" "}
                      {l.url.startsWith("https://") ? (
                        <a
                          href={l.url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="underline hover:text-slate-100"
                        >
                          {l.url}
                        </a>
                      ) : (
                        l.url
                      )}
                    </p>
                  </div>
                ))}
            </section>
          ) : null}
          <p>
            <ItemLinkView link={{ page: "migration/dependencies", item: library.row_id }} testId="open-in">
              Open in Dependencies
            </ItemLinkView>
          </p>
          <RelatedFor itemKey={`library:${library.row_id}`} />
        </div>
      ) : null}
    </DetailPanel>
  );
}
