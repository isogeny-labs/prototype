import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { ProjectOverview, ProjectOverviewRow } from "../api";
import App from "../App";
import { calls, mockApi, session, text } from "./fixtures";
import { FULL_COUNTS, acmePayView, workspace } from "./shellFixtures";

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/p/10");
});

const OPEN = { key: "open", label: "Open", closed_line: null, signoff: null } as const;
const SIGNED = {
  key: "closed",
  label: "Closed",
  closed_line: "Signed off by Dana Lee. This assessment is closed. Start a new one to continue.",
  signoff: { by: "Dana Lee", note: null, at: "2026-11-11T09:00:00Z" },
} as const;

function row(id: number, number: number, over: Partial<ProjectOverviewRow> = {}): ProjectOverviewRow {
  return {
    id,
    number,
    title: `Assessment ${number}`,
    name: null,
    purpose: { key: "full_review", label: "Full review" },
    reference: null,
    status: OPEN,
    archived: false,
    created_at: "2026-11-10T09:00:00Z",
    closed_at: null,
    file: { import_id: id, filename: "acme-pay-cbom.json", format: "cyclonedx-cbom", is_demo: true, imported_at: "2026-11-10T09:05:00Z" },
    headline: { ...FULL_COUNTS, blockers: 1 },
    has_results: true,
    ...over,
  };
}

const link = (page: string, item: string | null, assessment_id: number) => ({ page, item, group: null, assessment_id });

const overview: ProjectOverview = {
  id: 10,
  rows: [
    row(101, 2, { purpose: { key: "release_check", label: "Release check" }, reference: "Release 2.1" }),
    row(100, 1, { status: SIGNED, closed_at: "2026-11-11T09:00:00Z", headline: { claims: null, tests: null, fixes: null, systems: null, blockers: null } }),
  ],
  compare: {
    from_id: 100,
    to_id: 101,
    lists: [
      { key: "new", title: "New findings", items: [{ label: "Old TLS versions", sub: "Failed in Assessment 2", link: link("evidence", "test-3", 101) }] },
      { key: "gone", title: "No longer findings", items: [] },
      { key: "moved", title: "Tracks that moved", items: [{ label: "localhost:8451 · Key exchange", sub: "Classical to Hybrid", link: link("migration/systems", "server:localhost:8451", 101) }] },
      { key: "single", title: "Not checked in both", items: [] },
    ],
  },
  shared: [{ name: "localhost:8443", kind: "server", assessments: [{ id: 101, title: "Assessment 2" }, { id: 100, title: "Assessment 1" }], note: null }],
  choices: [
    { id: 101, title: "Assessment 2" },
    { id: 100, title: "Assessment 1" },
  ],
};

function routes(extra: Record<string, unknown> = {}) {
  return {
    "GET /api/session": { body: session },
    "GET /api/workspace": { body: workspace },
    "GET /api/projects/10": { body: acmePayView },
    "GET /api/projects/10/overview": { body: overview },
    ...extra,
  } as Parameters<typeof mockApi>[0];
}

async function show(extra: Record<string, unknown> = {}) {
  const fetchMock = mockApi(routes(extra));
  render(<App />);
  await screen.findAllByTestId("assessment-row");
  return fetchMock;
}

const rows = () => screen.getAllByTestId("assessment-row");

describe("Project overview", () => {
  it("lists every assessment of the project side by side, with its purpose, status and sign-off, newest first", async () => {
    await show();
    expect(screen.getByRole("heading", { level: 1, name: "Acme Pay" })).not.toBeNull();
    expect(text(screen.getByTestId("page-header"))).toContain("2 assessments: 1 open, 1 closed.");
    expect(rows()).toHaveLength(2);
    expect(text(rows()[0]!)).toContain("Assessment 2");
    expect(text(rows()[0]!)).toContain("Release check · Release 2.1 · acme-pay-cbom.json");
    expect(text(rows()[0]!)).toContain("Open");
    expect(text(rows()[1]!)).toContain("Closed");
    expect(text(rows()[1]!)).toMatch(/by Dana Lee, /);
  });

  it("shows each assessment's headline counts as its pages count them, and Not yet where nothing happened", async () => {
    await show();
    const first = text(rows()[0]!);
    for (const words of ["12 checked", "3 false", "2 failed", "of 5 run", "2 open", "of 4", "3 Classical", "2 Hybrid"]) expect(first).toContain(words);
    expect(text(rows()[1]!).match(/Not yet/g)?.length).toBeGreaterThanOrEqual(4);
    expect(text(screen.getByTestId("project-overview"))).not.toMatch(/\bscore\b|\bgrade\b|secure|trend|time to hack/i);
  });

  it("opens an assessment from its row", async () => {
    await show({ "GET /api/assessments/100": { body: null } });
    fireEvent.click(rows()[1]!);
    await waitFor(() => expect(window.location.hash).toBe("#/a/100/overview"));
  });

  it("What changed: four lists between the two picked assessments, each entry a link to the item", async () => {
    const fetchMock = await show({ "GET /api/projects/10/overview?from_id=101&to_id=101": { body: overview } });
    const changed = within(screen.getByTestId("what-changed"));
    expect(changed.getAllByTestId("compare-list").map((l) => [l.getAttribute("data-list"), text(l.querySelector("h3"))])).toEqual([
      ["new", "New findings"],
      ["gone", "No longer findings"],
      ["moved", "Tracks that moved"],
      ["single", "Not checked in both"],
    ]);
    expect(changed.getByRole("link", { name: "Old TLS versions" }).getAttribute("href")).toBe("#/a/101/evidence?item=test-3");
    expect(changed.getByRole("link", { name: "localhost:8451 · Key exchange" }).getAttribute("href")).toBe(
      "#/a/101/migration/systems?item=server%3Alocalhost%3A8451",
    );
    expect((changed.getByRole("combobox", { name: "From" }) as HTMLSelectElement).value).toBe("100");
    expect((changed.getByRole("combobox", { name: "To" }) as HTMLSelectElement).value).toBe("101");
    // Picking another pair asks for it; the page works nothing out itself.
    fireEvent.change(changed.getByRole("combobox", { name: "From" }), { target: { value: "101" } });
    await waitFor(() => expect(calls(fetchMock)).toContain("GET /api/projects/10/overview?from_id=101&to_id=101"));
  });

  it("names the systems more than one assessment checked", async () => {
    await show();
    const shared = screen.getByTestId("shared-systems");
    expect(text(shared)).toContain("localhost:8443");
    expect(text(shared)).toContain("in Assessment 2, Assessment 1");
  });

  it("says what fills What changed when the project has one assessment", async () => {
    await show({ "GET /api/projects/10/overview": { body: { ...overview, rows: [overview.rows[0]!], compare: null, shared: [], choices: [overview.choices[0]!] } } });
    expect(screen.queryByTestId("what-changed")).toBeNull();
    expect(text(screen.getByTestId("project-overview"))).toContain("What changed shows once the project has two assessments.");
    expect(text(screen.getByTestId("project-overview"))).toContain("No system is named by more than one assessment of this project.");
  });

  it("New assessment opens the box, and Start makes it in this project and opens it", async () => {
    const fetchMock = await show({
      "POST /api/projects/10/assessments": { body: { id: 102 } },
      "GET /api/assessments/102": { body: null },
    });
    fireEvent.click(within(screen.getByTestId("page-header")).getByRole("button", { name: "New assessment" }));
    const box = within(await screen.findByTestId("new-assessment-box"));
    // The name the box suggests comes with the project's data, in a request of its own, so it is waited for.
    await waitFor(() => expect((box.getByLabelText("Name") as HTMLInputElement).value).toBe("Assessment 3"));
    fireEvent.click(box.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/overview"));
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual(["POST /api/projects/10/assessments"]);
  });

  it("Show archived asks for the archived assessments too", async () => {
    const fetchMock = await show({ "GET /api/projects/10/overview?archived=true": { body: overview } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Show archived" }));
    await waitFor(() => expect(calls(fetchMock)).toContain("GET /api/projects/10/overview?archived=true"));
  });
});
