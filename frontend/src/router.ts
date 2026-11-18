import { useCallback, useEffect, useState } from "react";

/** Phase 5a: where the app is, kept in the address bar's #part, so refresh and back/forward work. No router package.
 * Phase 5b: a project has its own overview (#/p/<id>), Tests is now Checks, and an address can name one item on a page
 * (#/a/<id>/<page>?item=<id>&group=<group>), so a link opens exactly that item and Back returns.
 * Phase 5c: Advisories is a page of every assessment (between Inventory and Checks), and Settings can open on one of
 * its sections (#/settings?section=test-packs). */
export type Page =
  | "overview"
  | "inventory/import"
  | "inventory/verify"
  | "advisories"
  | "checks"
  | "evidence"
  | "fixes"
  | "migration/systems"
  | "migration/roadmap"
  | "migration/dependencies";

export const PAGES: Page[] = [
  "overview",
  "inventory/import",
  "inventory/verify",
  "advisories",
  "checks",
  "evidence",
  "fixes",
  "migration/systems",
  "migration/roadmap",
  "migration/dependencies",
];

export type AssessmentRoute = {
  kind: "assessment";
  id: number;
  page: Page;
  /** One item to open on the page: a claim, check, fix, system or library id. */
  item?: string | null;
  /** The work group to filter the page to. */
  group?: string | null;
  section?: string | null;
};

/** Settings may name one of its sections to open on (phase 5c: "test-packs"). */
export type SettingsRoute = { kind: "settings"; section?: string | null };

export type Route = { kind: "projects" } | SettingsRoute | { kind: "project"; id: number } | AssessmentRoute;

function pageOf(text: string | undefined): Page {
  if (text === "tests") return "checks"; // the phase 5a address of Tests still opens it
  return (PAGES as string[]).includes(text ?? "") ? (text as Page) : "overview";
}

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [path = "", query = ""] = raw.split("?", 2);
  if (path === "settings") {
    const section = new URLSearchParams(query).get("section");
    return section ? { kind: "settings", section } : { kind: "settings" };
  }
  const p = /^p\/(\d+)$/.exec(path);
  if (p) return { kind: "project", id: Number(p[1]) };
  const m = /^a\/(\d+)(?:\/(.+))?$/.exec(path);
  if (m) {
    const params = new URLSearchParams(query);
    return {
      kind: "assessment",
      id: Number(m[1]),
      page: pageOf(m[2]),
      item: params.get("item"),
      group: params.get("group"),
      section: params.get("section"),
    };
  }
  return { kind: "projects" };
}

export function routeHref(route: Route): string {
  if (route.kind === "settings") return route.section ? `#/settings?${new URLSearchParams({ section: route.section }).toString()}` : "#/settings";
  if (route.kind === "project") return `#/p/${route.id}`;
  if (route.kind === "assessment") {
    const params = new URLSearchParams();
    if (route.item) params.set("item", route.item);
    if (route.group) params.set("group", route.group);
    if (route.section) params.set("section", route.section);
    const query = params.toString();
    return `#/a/${route.id}/${route.page}${query ? `?${query}` : ""}`;
  }
  return "#/projects";
}

export function pageHref(id: number, page: Page, item?: string | null, group?: string | null): string {
  return routeHref({ kind: "assessment", id, page, item, group });
}

/** A link the backend sent (page and item): where it goes, in this assessment or the one it names. Phase 5c: a link
 * whose page is "settings" opens Settings (on the section it names), which belongs to no assessment. */
export function linkRoute(
  link: { page: string; item?: string | null; group?: string | null; section?: string | null; assessment_id?: number | null },
  assessmentId: number,
): AssessmentRoute | SettingsRoute {
  if (link.page === "settings") return link.section ? { kind: "settings", section: link.section } : { kind: "settings" };
  return {
    kind: "assessment",
    id: link.assessment_id ?? assessmentId,
    page: pageOf(link.page),
    item: link.item ?? null,
    group: link.group ?? null,
    section: link.section ?? null,
  };
}

export function useRoute(): [Route, (next: Route, replace?: boolean) => void] {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: Route, replace = false) => {
    const href = routeHref(next);
    if (replace) window.history.replaceState(null, "", href);
    else if (window.location.hash !== href) window.history.pushState(null, "", href);
    setRoute(parseRoute(href));
  }, []);
  return [route, navigate];
}
