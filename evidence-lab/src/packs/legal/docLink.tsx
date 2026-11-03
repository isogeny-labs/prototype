import { Link } from "react-router-dom";
import type { Artifact, DocumentLocation } from "@/contracts";
import { locationLabel } from "@/lib/lookup";

/** Link into the document viewer panel on the workspace at a page and line. */
export function DocLink({ projectId, artifacts, loc, children }: { projectId: string; artifacts: Artifact[]; loc: DocumentLocation; children?: React.ReactNode }) {
  const q = new URLSearchParams({ doc: loc.artifactVersionId, page: String(loc.page), ...(loc.line ? { line: String(loc.line) } : {}) });
  return <Link to={`/p/${projectId}?${q.toString()}#panel-documents`} data-testid="doc-link">{children ?? locationLabel(artifacts, loc)}</Link>;
}
