import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useProject } from "@/shell/ProjectContext";
import { EmptyState, PageHeader, ProposalCard, QueryBoundary } from "@/components";
import { byId } from "@/lib/lookup";

export function ResearchPage() {
  const { project } = useProject();
  const q = useQuery(async () => ({ proposals: await services.autoresearcher.list(project.id), runs: await services.evidenceLab.listRuns(project.id) }), [project.id]);
  return (
    <>
      <PageHeader title="Research" subtitle="Experiment proposals from the Autoresearcher (simulated). A proposal runs only under an approved, numbered protocol; results link to runs; follow-ups are suggestions, never auto-executed." />
      <QueryBoundary q={q} label="Loading proposals">{({ proposals, runs }) => proposals.length === 0 ? <EmptyState title="No proposals yet" hint="Proposals are generated from findings and reviewed before anything runs." /> : (
        <div className="grid gap-4">{proposals.map((p) => <ProposalCard key={p.id} proposal={p} runsById={byId(runs)} projectId={project.id} />)}</div>
      )}</QueryBoundary>
      <div className="callout-sample mt-4 text-xs">The Autoresearcher is simulated: proposals here are sample data and the model label reads "sample-model (no real model connected)".</div>
    </>
  );
}
