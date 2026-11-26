import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type ItemLink, type RelatedLine } from "../api";
import { linkRoute, routeHref } from "../router";
import { FoldLine } from "./foldline";

/** Phase 5b: links between items. Every link the backend sends names a page and an item; this turns it into an address
 * in the open assessment (or the one it names), so a link opens exactly that item and Back returns. */
const AssessmentLinks = createContext<{ assessmentId: number; planId: number | null } | null>(null);

export function LinkProvider({
  assessmentId,
  planId,
  children,
}: {
  assessmentId: number;
  planId: number | null;
  children: ReactNode;
}) {
  return <AssessmentLinks.Provider value={{ assessmentId, planId }}>{children}</AssessmentLinks.Provider>;
}

export function useLinkHref(): (link: ItemLink) => string {
  const ctx = useContext(AssessmentLinks);
  // Phase 5c: a link to Settings (the Test packs section) belongs to no assessment, so it needs none open.
  return (link) =>
    ctx ? routeHref(linkRoute(link, ctx.assessmentId)) : link.page === "settings" ? routeHref(linkRoute(link, 0)) : "#";
}

export function usePlanId(): number | null {
  return useContext(AssessmentLinks)?.planId ?? null;
}

/** A link to one item, as the backend named it. */
export function ItemLinkView({
  link,
  children,
  className,
  testId,
}: {
  link: ItemLink;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  const href = useLinkHref();
  return (
    <a
      href={href(link)}
      data-testid={testId}
      className={className ?? "text-sky-300 underline-offset-2 hover:underline"}
    >
      {children}
    </a>
  );
}

/** The Related block of a detail panel: up to six lines (Claim, Checks, Fix, System and track, Library, and since phase
 * 5c Advisory), each shown only when the backend recorded the relation, under the title the backend gave it. Every
 * entry opens that item on its own page. */
export function RelatedBlock({
  lines,
  bare = false,
}: {
  lines: RelatedLine[] | null;
  /** Inside a fold that already says "Related": no box and no heading of its own. */
  bare?: boolean;
}) {
  if (!lines || lines.length === 0) return null;
  return (
    <section
      data-testid="related"
      aria-label="Related"
      className={bare ? "min-w-0" : "mt-5 rounded-lg border border-slate-800 bg-slate-900/50 p-3"}
    >
      {bare ? null : <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Related</h3>}
      <dl className="space-y-2 text-sm">
        {lines.map((line) => (
          <div
            key={line.kind}
            data-testid="related-line"
            data-kind={line.kind}
            className="grid gap-1 @sm:grid-cols-[8rem_minmax(0,1fr)]"
          >
            <dt className="text-xs text-slate-500">{line.title}</dt>
            <dd className="space-y-1">
              {line.items.map((item) => (
                <div key={item.key}>
                  <ItemLinkView link={item.link} testId="related-link">
                    {item.label}
                  </ItemLinkView>
                  {item.sub ? <span className="block text-xs text-slate-400">{item.sub}</span> : null}
                </div>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The Related block of one item, asked of the backend (a claim, a test, a fix, a system, a library or an advisory). */
export function useRelated(planId: number | null, key: string | null): RelatedLine[] | null {
  const [lines, setLines] = useState<RelatedLine[] | null>(null);
  useEffect(() => {
    let live = true;
    setLines(null);
    if (planId === null || key === null) return;
    api
      .getRelated(planId, key)
      .then((view) => {
        if (live) setLines(view.related);
      })
      .catch(() => {
        if (live) setLines([]);
      });
    return () => {
      live = false;
    };
  }, [planId, key]);
  return lines;
}

/** The Related block for an item, fetched by itself (for panels whose page doesn't already have it). */
export function RelatedFor({ itemKey }: { itemKey: string | null }) {
  const planId = usePlanId();
  const lines = useRelated(planId, itemKey);
  return <RelatedBlock lines={lines} />;
}

/** The design refactor (26 November 2026): the Related block as a quiet folded line at the foot of a panel, with how
 * many items it holds and which kinds. The same links are drawn as the trail at the top of the panel. */
export function RelatedFold({ lines }: { lines: RelatedLine[] | null }) {
  if (!lines || lines.length === 0) return null;
  const count = lines.reduce((n, l) => n + l.items.length, 0);
  return (
    <FoldLine
      title="Related"
      count={count}
      hint={lines.map((l) => l.title.toLowerCase()).join(", ")}
      testId="related-fold"
    >
      <RelatedBlock lines={lines} bare />
    </FoldLine>
  );
}

/** Asks for an item's related lines once, for a panel that draws them twice (the trail on top, the fold at the foot). */
export function WithRelated({
  itemKey,
  children,
}: {
  itemKey: string | null;
  children: (lines: RelatedLine[] | null) => ReactNode;
}) {
  const planId = usePlanId();
  const lines = useRelated(planId, itemKey);
  return <>{children(lines)}</>;
}
