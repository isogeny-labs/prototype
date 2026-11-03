import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmptyState, Marker } from "@/components";
import { allVersions } from "@/lib/lookup";
import type { PackPanelProps } from "../types";

/** Read-only viewer with page and line numbers. Deep links: ?doc=<artifactVersionId>&page=<n>&line=<n>. */
export function DocumentViewerPanel({ data }: PackPanelProps) {
  const [params] = useSearchParams();
  const docs = useMemo(() => allVersions(data.artifacts).filter((v) => v.packData?.packId === "legal" && v.packData.pages?.length), [data.artifacts]);
  const [docId, setDocId] = useState<string>(params.get("doc") ?? docs[0]?.id ?? "");
  const [page, setPage] = useState<number>(Number(params.get("page") ?? 1));
  const line = Number(params.get("line") ?? 0);
  useEffect(() => { const d = params.get("doc"); if (d) { setDocId(d); setPage(Number(params.get("page") ?? 1)); } }, [params]);
  const doc = docs.find((d) => d.id === docId) ?? docs[0];
  const pages = doc?.packData?.packId === "legal" ? doc.packData.pages ?? [] : [];
  const current = pages.find((p) => p.page === page) ?? pages[0];
  const ref = useRef<HTMLOListElement>(null);
  useEffect(() => { if (line && ref.current) { const el = ref.current.querySelector(`[data-line="${line}"]`); el?.scrollIntoView({ block: "center" }); } }, [line, docId, page]);
  if (!doc || !current) return <EmptyState title="No documents with viewable text" />;
  const privileged = doc.packData?.packId === "legal" && doc.packData.privileged;
  return (
    <div data-testid="document-viewer">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <label>Document <select className="input ml-1 w-auto max-w-xs" value={doc.id} onChange={(e) => { setDocId(e.target.value); setPage(1); }} data-testid="doc-select">{docs.map((d) => <option key={d.id} value={d.id}>{d.artifactName} ({d.version})</option>)}</select></label>
        <label>Page <select className="input ml-1 w-auto" value={current.page} onChange={(e) => setPage(Number(e.target.value))}>{pages.map((p) => <option key={p.page} value={p.page}>{p.page}</option>)}</select></label>
        {doc.packData?.packId === "legal" ? <span className="tag">{doc.packData.documentType}</span> : null}
        {privileged ? <span className="tag border-warn/60 text-warn">Privileged</span> : null}
        <Marker kind="fictional" className="ml-auto" />
      </div>
      <ol ref={ref} className="max-h-80 overflow-y-auto rounded bg-bg p-3 font-mono text-xs" aria-label={`${doc.artifactName} page ${current.page}`}>
        {current.lines.map((text, i) => { const n = i + 1; const hit = n === line; return (
          <li key={n} data-line={n} className={`grid grid-cols-[2.5rem_minmax(0,1fr)] gap-2 whitespace-pre-wrap py-0.5 ${hit ? "bg-warn/20 text-ink" : "text-muted"}`}><span className="select-none text-right text-faint">{n}</span><span>{text || " "}</span></li>
        ); })}
      </ol>
      <div className="mt-1 text-xs text-faint">Read-only. Document-handling controls (privilege tagging, redaction, access logging) are integration pending.</div>
    </div>
  );
}
