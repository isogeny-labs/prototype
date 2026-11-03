import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { ArtifactVersionList, EmptyState, PageHeader, QueryBoundary } from "@/components";

export function ArtifactsPage() {
  const { project, template } = useProject();
  const q = useQuery(() => services.evidenceLab.listArtifacts(project.id), [project.id]);
  return (
    <>
      <PageHeader title="Artifacts" subtitle={<>Versioned inputs with hashes and provenance. Supported kinds for this template: {template.supportedArtifactTypes.join(", ")}. Importing a new version never overwrites an old one.</>} />
      <QueryBoundary q={q} label="Loading artifacts">{(artifacts) => artifacts.length === 0 ? <EmptyState title="No artifacts imported" hint="Import a library, configuration or test-vector file to begin." /> : (
        <div className="grid gap-4">{artifacts.map((a) => <ArtifactVersionList key={a.id} artifact={a} project={project} />)}</div>
      )}</QueryBoundary>
    </>
  );
}
