import { EmptyState } from "@/components";
import { allVersions } from "@/lib/lookup";
import type { PackPanelProps } from "../types";
import { DocLink } from "./docLink";

export function AuthoritiesPanel({ project, data }: PackPanelProps) {
  const auths = allVersions(data.artifacts).filter((v) => v.packData?.packId === "legal" && v.packData.authority);
  if (auths.length === 0) return <EmptyState title="No authorities imported" />;
  return (
    <table className="tbl" data-testid="authorities">
      <thead><tr><th>Authority</th><th>Stands for (in this sample)</th><th>Role</th><th>Text</th></tr></thead>
      <tbody>{auths.map((v) => { const a = v.packData?.packId === "legal" ? v.packData.authority : undefined; if (!a) return null; return (
        <tr key={v.id} data-testid="authority-row">
          <td><div className="font-medium">{a.name}</div><div className="text-xs text-muted">{a.court}, {a.year}</div><span className="tag mt-1 border-sample/60 text-sample" data-testid="fictional-label">{a.fictionalLabel}</span></td>
          <td>{a.proposition}</td>
          <td>{a.contrary ? <span className="tag border-warn/60 text-warn">● Contrary</span> : a.reliedOnInBrief ? <span className="tag border-ok/60 text-ok">▲ Relied on</span> : <span className="tag">—</span>}</td>
          <td className="text-xs"><DocLink projectId={project.id} artifacts={data.artifacts} loc={{ artifactVersionId: v.id, page: 1, label: a.name }}>open text</DocLink></td>
        </tr>
      ); })}</tbody>
    </table>
  );
}
