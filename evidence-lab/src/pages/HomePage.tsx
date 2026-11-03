import { Link } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { EmptyState, Marker, PackBadge, PageHeader, QueryBoundary } from "@/components";
import { fmtDate, humanize } from "@/lib/format";
import { toUserFacingStatus } from "@/contracts";
import { byId } from "@/lib/lookup";

export function HomePage() {
  const q = useQuery(async () => {
    const [projects, packs, templates] = await Promise.all([services.evidenceLab.listProjects(), services.packs.listPacks(), services.packs.listTemplates()]);
    const extras = await Promise.all(projects.map(async (p) => {
      const [approvals, runs, findings] = await Promise.all([services.approvals.list(p.id), services.evidenceLab.listRuns(p.id), services.evidenceLab.listFindings(p.id)]);
      return { id: p.id, pending: approvals.filter((a) => a.decision === "pending").length, runs: runs.length, lastRun: runs.at(-1)?.createdAt ?? null, openFindings: findings.filter((f) => !["Resolved within tested scope", "Not relevant"].includes(toUserFacingStatus(f, byId(runs)))).length };
    }));
    return { projects, packs, templates, extras: Object.fromEntries(extras.map((e) => [e.id, e])) };
  }, []);
  return (
    <>
      <PageHeader title="Projects" subtitle="One shared workflow (intake → artifacts → tests → runs → findings → approvals → changes → reports) with pack-specific templates. Everything shown is sample data." />
      <QueryBoundary q={q} label="Loading projects">{({ projects, packs, templates, extras }) => (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <section>
            <h2 className="h3 mb-2">Your projects</h2>
            {projects.length === 0 ? <EmptyState title="No projects yet" hint="Sample data was reset or removed. Load it again from Sample data settings." /> : (
              <div className="grid gap-3">
                {projects.map((p) => { const e = extras[p.id]; const tpl = templates.find((t) => t.id === p.templateId); return (
                  <Link key={p.id} to={`/p/${p.id}`} className="panel block no-underline text-ink hover:border-accent" data-testid="project-card">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="h2">{p.name}</span>
                      <PackBadge packId={p.packId} templateName={tpl ? `${tpl.name} v${tpl.version}` : undefined} />
                      {p.isSample ? <Marker kind="sample" /> : null}
                      <span className="ml-auto tag">{humanize(p.status)}</span>
                    </div>
                    <p className="mt-2 text-sm text-muted">{p.summary}</p>
                    <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
                      <span><strong className="text-ink">{e?.openFindings ?? 0}</strong> unresolved findings</span>
                      <span><strong className="text-ink">{e?.pending ?? 0}</strong> pending approvals</span>
                      <span><strong className="text-ink">{e?.runs ?? 0}</strong> runs · last {fmtDate(e?.lastRun)}</span>
                      <span>created {fmtDate(p.createdAt)}</span>
                    </div>
                  </Link>
                ); })}
              </div>
            )}
          </section>
          <section>
            <h2 className="h3 mb-2">Packs</h2>
            <div className="grid gap-3">
              {packs.map((pk) => (
                <div key={pk.id} className="panel text-sm" data-testid="pack-card">
                  <div className="flex items-center gap-2"><PackBadge packId={pk.id} /><span className={`ml-auto tag ${pk.status === "sample_available" ? "border-ok/60 text-ok" : ""}`}>{pk.status === "sample_available" ? "Sample available" : "Coming in Phase 2"}</span></div>
                  <p className="mt-2 text-muted">{pk.tagline}</p>
                  <div className="mt-2 text-xs text-faint">Templates: {pk.templateIds.map((id) => templates.find((t) => t.id === id)?.name ?? id).join(", ")}</div>
                </div>
              ))}
            </div>
            <div className="callout-info mt-4">Nothing on these pages is a security score, a certification or a prediction. Labels are computed from checks and reviewers; see any finding for how.</div>
          </section>
        </div>
      )}</QueryBoundary>
    </>
  );
}
