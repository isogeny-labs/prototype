import { useCallback, useEffect, useState } from "react";

/** Phase 5a: where the app is, kept in the address bar's #part, so refresh and back/forward work. No router package. */
export type Page =
  | "overview"
  | "inventory/import"
  | "inventory/verify"
  | "tests"
  | "evidence"
  | "fixes"
  | "migration/systems"
  | "migration/roadmap"
  | "migration/dependencies";

export const PAGES: Page[] = [
  "overview",
  "inventory/import",
  "inventory/verify",
  "tests",
  "evidence",
  "fixes",
  "migration/systems",
  "migration/roadmap",
  "migration/dependencies",
];

export type Route = { kind: "projects" } | { kind: "settings" } | { kind: "assessment"; id: number; page: Page };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  if (path === "settings") return { kind: "settings" };
  const m = /^a\/(\d+)(?:\/(.+))?$/.exec(path);
  if (m) {
    const page = (PAGES as string[]).includes(m[2] ?? "") ? (m[2] as Page) : "overview";
    return { kind: "assessment", id: Number(m[1]), page };
  }
  return { kind: "projects" };
}

export function routeHref(route: Route): string {
  if (route.kind === "settings") return "#/settings";
  if (route.kind === "assessment") return `#/a/${route.id}/${route.page}`;
  return "#/projects";
}

export function pageHref(id: number, page: Page): string {
  return routeHref({ kind: "assessment", id, page });
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
