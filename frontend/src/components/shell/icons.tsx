/** Small line icons for the sidebar (drawn here; no icon package). Decorative: the words beside them carry the meaning. */
const PATHS: Record<string, string> = {
  overview: "M4 5h7v6H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 13h7v6H4z",
  inventory: "M5 6h14M5 12h14M5 18h9",
  import: "M12 4v11m0 0-4-4m4 4 4-4M5 20h14",
  verify: "M5 12.5 9.5 17 19 7",
  advisories: "M4 10v4h3l6 4V6l-6 4zM16.5 9.5a3.5 3.5 0 0 1 0 5M19 7a7 7 0 0 1 0 10",
  tests: "M9 3h6M10 3v6l-5 9a1.5 1.5 0 0 0 1.3 2.2h11.4A1.5 1.5 0 0 0 19 18l-5-9V3",
  evidence: "M7 3h7l5 5v13H7zM14 3v5h5M10 14l2 2 4-4",
  fixes: "M14.5 5.5a4 4 0 0 0-5.3 5.3L4 16l4 4 5.2-5.2a4 4 0 0 0 5.3-5.3l-2.6 2.6-2.4-.6-.6-2.4z",
  migration: "M4 7h11l-3-3m3 3-3 3M20 17H9l3 3m-3-3 3-3",
  systems: "M5 5h14v5H5zM5 14h14v5H5zM8 7.5h.01M8 16.5h.01",
  roadmap: "M4 6h6v4H4zM10 8h4M14 6h6v4h-6zM14 16h6v4h-6zM17 10v6",
  dependencies: "M12 3 4 7.5v9L12 21l8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9",
  projects: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1",
  collapse: "M15 6l-6 6 6 6",
  expand: "M9 6l6 6-6 6",
  menu: "M4 7h16M4 12h16M4 17h16",
  chevron: "M8 10l4 4 4-4",
  assistant: "M5 5h14v10H9l-4 4z",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  project: "M6 4h12v16H6zM9 8h6M9 12h6M9 16h3",
};

export function Icon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className={`shrink-0 ${className}`}>
      <path d={PATHS[name] ?? PATHS.overview} />
    </svg>
  );
}
