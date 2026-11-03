import type { Artifact, Project } from "@/contracts";
import { fmtBytes, fmtDateTime, humanize, shortSha } from "@/lib/format";
import { actorName } from "@/lib/lookup";
import { Marker } from "./Marker";

const PROV: Record<string, string> = { user_reported: "User-reported", imported: "Imported", detected: "Detected", independently_tested: "Independently tested" };

export function ArtifactVersionList({ artifact, project }: { artifact: Artifact; project: Project | null }) {
  const versions = [...artifact.versions].sort((a, b) => (a.importedAt < b.importedAt ? 1 : -1));
  return (
    <section className="panel text-sm" data-testid="artifact">
      <div className="flex flex-wrap items-center gap-2">
        <span className="tag">{humanize(artifact.kind)}</span>
        <h3 className="font-semibold">{artifact.name}</h3>
        <span className="ml-auto text-xs text-faint">{artifact.versions.length} version{artifact.versions.length === 1 ? "" : "s"}</span>
      </div>
      <p className="mt-1 text-muted">{artifact.description}</p>
      <ol className="mt-3 space-y-2">
        {versions.map((v) => (
          <li key={v.id} className="panel-2" data-testid="artifact-version" id={v.id}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-semibold">{v.version}</span>
              <span className="tag" title={`Provenance: ${PROV[v.provenance] ?? v.provenance}`}>{PROV[v.provenance] ?? v.provenance}</span>
              {v.parentVersionId ? <span className="text-xs text-muted">supersedes {artifact.versions.find((p) => p.id === v.parentVersionId)?.version ?? v.parentVersionId}</span> : <span className="text-xs text-faint">first version</span>}
              {v.seededDefect ? <span className="tag border-sample/60 text-sample" title={v.seededDefect}>◇ Planted sample defect</span> : null}
              <span className="ml-auto text-xs text-faint">{fmtDateTime(v.importedAt)} · {actorName(project, v.importedBy)}</span>
            </div>
            <dl className="kv mt-2">
              <dt>SHA-256</dt><dd><code className="text-xs" title={v.sha256}>{shortSha(v.sha256, 24)}</code></dd>
              <dt>Size</dt><dd>{fmtBytes(v.sizeBytes)}</dd>
              <dt>Preview</dt><dd className="text-muted">{v.preview}</dd>
              {v.notes ? <><dt>Notes</dt><dd>{v.notes}</dd></> : null}
              {v.seededDefect ? <><dt>Planted defect</dt><dd className="text-muted">{v.seededDefect} <Marker kind="fictional" /></dd></> : null}
            </dl>
          </li>
        ))}
      </ol>
    </section>
  );
}
