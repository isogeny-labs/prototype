import type { ArgumentNode } from "@/contracts";
import { EmptyState } from "@/components";
import { versionLabel } from "@/lib/lookup";
import type { PackPanelProps } from "../types";
import { DocLink } from "./docLink";

const STATUS: Record<ArgumentNode["status"], { label: string; cls: string; glyph: string }> = {
  supported: { label: "Supported", cls: "border-ok/60 text-ok", glyph: "▲" }, unsupported: { label: "Unsupported", cls: "border-bad/60 text-bad", glyph: "▼" },
  disputed: { label: "Disputed", cls: "border-warn/60 text-warn", glyph: "●" }, revised: { label: "Revised in v2", cls: "border-info/60 text-info", glyph: "↺" }, open: { label: "Open", cls: "", glyph: "○" },
};
const KIND: Record<ArgumentNode["kind"], string> = { claim: "Claim", fact: "Fact", authority: "Authority (fictional)", counter: "Counterargument", response: "Response" };

export function ArgumentMapPanel({ project, data }: PackPanelProps) {
  if (project.packData.packId !== "legal") return null;
  const nodes = project.packData.argumentMap;
  if (nodes.length === 0) return <EmptyState title="No argument map yet" />;
  const claims = nodes.filter((n) => n.kind === "claim");
  const supportersOf = (id: string) => nodes.filter((n) => n.supports.includes(id) && n.kind !== "counter" && n.kind !== "response");
  const countersOf = (id: string) => nodes.filter((n) => n.kind === "counter" && n.supports.includes(id));
  const responsesTo = (id: string) => nodes.filter((n) => n.kind === "response" && n.supports.includes(id));
  const Node = ({ n }: { n: ArgumentNode }) => { const s = STATUS[n.status]; return (
    <div className="panel-2 text-sm" data-testid="argument-node" data-kind={n.kind}>
      <div className="flex flex-wrap items-center gap-2"><span className="tag">{KIND[n.kind]}</span><span className={`tag ${s.cls}`}>{s.glyph} {s.label}</span><span className="font-mono text-xs text-faint">{n.id}</span></div>
      <div className="mt-1">{n.text}</div>
      {n.source && "artifactVersionId" in n.source ? <div className="text-xs">Source: <DocLink projectId={project.id} artifacts={data.artifacts} loc={n.source} /></div> : null}
      {n.source && "authorityArtifactVersionId" in n.source ? <div className="text-xs text-muted">Authority: {versionLabel(data.artifacts, n.source.authorityArtifactVersionId)} · Sample authority, not a real case</div> : null}
      {n.note ? <div className="text-xs text-faint">{n.note}</div> : null}
    </div>
  ); };
  return (
    <div className="grid gap-4 xl:grid-cols-2" data-testid="argument-map">
      {claims.map((c) => (
        <div key={c.id} className="space-y-2">
          <Node n={c} />
          <div className="ml-4 space-y-2 border-l border-line pl-3">
            <div className="h3">Supports</div>
            {supportersOf(c.id).map((n) => <Node key={n.id} n={n} />)}
            {countersOf(c.id).length > 0 ? <div className="h3 mt-2">Against</div> : null}
            {countersOf(c.id).map((x) => <div key={x.id} className="space-y-2"><Node n={x} />{responsesTo(x.id).map((r) => <div key={r.id} className="ml-4 border-l border-line pl-3"><Node n={r} /></div>)}</div>)}
          </div>
        </div>
      ))}
    </div>
  );
}
