import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { OttoProjectBlock, ProjectOverview, ProjectOverviewRow } from "../api";
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
    file: {
      import_id: id,
      filename: "acme-pay-cbom.json",
      format: "cyclonedx-cbom",
      is_demo: true,
      imported_at: "2026-11-10T09:05:00Z",
    },
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
    row(100, 1, {
      status: SIGNED,
      closed_at: "2026-11-11T09:00:00Z",
      headline: { claims: null, tests: null, fixes: null, systems: null, blockers: null },
    }),
  ],
  compare: {
    from_id: 100,
    to_id: 101,
    lists: [
      {
        key: "new",
        title: "New findings",
        items: [{ label: "Old TLS versions", sub: "Failed in Assessment 2", link: link("evidence", "test-3", 101) }],
      },
      { key: "gone", title: "No longer findings", items: [] },
      {
        key: "moved",
        title: "Tracks that moved",
        items: [
          {
            label: "localhost:8451 · Key exchange",
            sub: "Classical to Hybrid",
            link: link("migration/systems", "server:localhost:8451", 101),
          },
        ],
      },
      { key: "single", title: "Not checked in both", items: [] },
    ],
  },
  shared: [
    {
      name: "localhost:8443",
      kind: "server",
      assessments: [
        { id: 101, title: "Assessment 2" },
        { id: 100, title: "Assessment 1" },
      ],
      note: null,
    },
  ],
  choices: [
    { id: 101, title: "Assessment 2" },
    { id: 100, title: "Assessment 1" },
  ],
};

/** "Otto in this project" (phase 5c) as the backend sends it: proposals waiting in each assessment, and what changed
 * since the newest test pack was installed. */
const OTTO: OttoProjectBlock = {
  title: "Otto in this project",
  note: "Each proposal is decided by a person. The counts below repeat what each assessment's own pages say.",
  pack_line: "Newest test pack: 2026.11.2, installed on 18 November 2026, 10:02 UTC.",
  since_title: "What changed since pack 2026.11.2",
  rows: [
    {
      assessment_id: 101,
      title: "Assessment 2",
      waiting: 2,
      waiting_text: "2 proposals waiting for a decision: 1 proposed check, 1 proposed fix",
      link: link("overview", null, 101),
      since: [
        "It brought 1 proposed check for this assessment: 1 waiting.",
        "2 decisions recorded since.",
        "Advisory checks run since: 1 Passed.",
      ],
    },
    {
      assessment_id: 100,
      title: "Assessment 1",
      waiting: 0,
      waiting_text: "Nothing waiting",
      link: link("overview", null, 100),
      since: ["It was closed before this pack was installed."],
    },
  ],
};
const OTTO_NO_PACK: OttoProjectBlock = {
  ...OTTO,
  pack_line: "No test pack is installed yet, so nothing is proposed.",
  since_title: null,
  rows: OTTO.rows.map((r) => ({ ...r, waiting: 0, waiting_text: "Nothing waiting", since: [] })),
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
    for (const words of ["12 checked", "3 false", "2 failed", "of 5 run", "2 open", "of 4", "3 Classical", "2 Hybrid"])
      expect(first).toContain(words);
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
    expect(
      changed.getAllByTestId("compare-list").map((l) => [l.getAttribute("data-list"), text(l.querySelector("h3"))]),
    ).toEqual([
      ["new", "New findings"],
      ["gone", "No longer findings"],
      ["moved", "Tracks that moved"],
      ["single", "Not checked in both"],
    ]);
    expect(changed.getByRole("link", { name: "Old TLS versions" }).getAttribute("href")).toBe(
      "#/a/101/evidence?item=test-3",
    );
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
    await show({
      "GET /api/projects/10/overview": {
        body: { ...overview, rows: [overview.rows[0]!], compare: null, shared: [], choices: [overview.choices[0]!] },
      },
    });
    expect(screen.queryByTestId("what-changed")).toBeNull();
    expect(text(screen.getByTestId("project-overview"))).toContain(
      "What changed shows once the project has two assessments.",
    );
    expect(text(screen.getByTestId("project-overview"))).toContain(
      "No system is named by more than one assessment of this project.",
    );
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

describe("Project overview: Otto in this project (phase 5c)", () => {
  const withOtto = (otto: OttoProjectBlock | null) => ({
    "GET /api/projects/10/overview": { body: { ...overview, otto } },
  });
  const block = () => screen.getByTestId("project-otto");
  const ottoRows = () => within(block()).getAllByTestId("project-otto-row");

  it("says for each assessment how many of Otto's proposals wait, as a link to that assessment, in the backend's words", async () => {
    const fetchMock = await show(withOtto(OTTO));
    expect(screen.getByRole("region", { name: "Otto in this project" })).toBe(block());
    expect(text(within(block()).getByTestId("project-otto-pack"))).toBe(OTTO.pack_line);
    expect(text(within(block()).getByTestId("project-otto-note"))).toBe(OTTO.note);
    expect(
      ottoRows().map((r) => [
        r.getAttribute("data-assessment"),
        r.getAttribute("data-waiting"),
        text(within(r).getByTestId("project-otto-link")),
        within(r).getByTestId("project-otto-link").getAttribute("href"),
        text(within(r).getByTestId("project-otto-waiting")),
      ]),
    ).toEqual([
      [
        "101",
        "2",
        "Assessment 2",
        "#/a/101/overview",
        "2 proposals waiting for a decision: 1 proposed check, 1 proposed fix",
      ],
      ["100", "0", "Assessment 1", "#/a/100/overview", "Nothing waiting"],
    ]);
    // A count that waits stands out calmly, as a chip with a symbol and its words; nothing waiting is plain text.
    expect(
      within(ottoRows()[0]!).getByTestId("project-otto-waiting").querySelector('[data-tone="warn"]'),
    ).not.toBeNull();
    expect(within(ottoRows()[1]!).getByTestId("project-otto-waiting").querySelector("[data-tone]")).toBeNull();
    // It holds no button, and looking at it sends nothing that changes anything.
    expect(within(block()).queryAllByRole("button")).toHaveLength(0);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("lists what changed since the newest test pack under that heading, line by line as sent", async () => {
    await show(withOtto(OTTO));
    expect(text(block())).toContain("What changed since pack 2026.11.2");
    expect(
      Array.from(within(ottoRows()[0]!).getByTestId("project-otto-since").querySelectorAll("li")).map((li) => text(li)),
    ).toEqual(OTTO.rows[0]!.since);
    expect(
      Array.from(within(ottoRows()[1]!).getByTestId("project-otto-since").querySelectorAll("li")).map((li) => text(li)),
    ).toEqual(["It was closed before this pack was installed."]);
  });

  it("sits with the assessments, before What changed", async () => {
    await show(withOtto(OTTO));
    const assessments = screen.getByRole("region", { name: "Assessments" });
    const changed = screen.getByRole("region", { name: "What changed" });
    expect(assessments.compareDocumentPosition(block()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(block().compareDocumentPosition(changed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("opens an assessment from its row's link", async () => {
    await show({ ...withOtto(OTTO), "GET /api/assessments/100": { body: null } });
    fireEvent.click(within(ottoRows()[1]!).getByTestId("project-otto-link"));
    await waitFor(() => expect(window.location.hash).toBe("#/a/100/overview"));
  });

  it("with no test pack installed it says so, and shows no heading and no line about a pack", async () => {
    await show(withOtto(OTTO_NO_PACK));
    expect(text(within(block()).getByTestId("project-otto-pack"))).toBe(
      "No test pack is installed yet, so nothing is proposed.",
    );
    expect(text(block())).not.toContain("What changed since");
    expect(within(block()).queryAllByTestId("project-otto-since")).toHaveLength(0);
    expect(ottoRows().map((r) => text(within(r).getByTestId("project-otto-waiting")))).toEqual([
      "Nothing waiting",
      "Nothing waiting",
    ]);
  });

  it("draws nothing when the answer carries no such block, or a null one", async () => {
    await show();
    expect(screen.queryByTestId("project-otto")).toBeNull();
  });

  it("draws nothing when the block is null", async () => {
    await show(withOtto(null));
    expect(screen.queryByTestId("project-otto")).toBeNull();
  });

  it("uses no score, grade or trend words, and adds none of its own", async () => {
    await show(withOtto(OTTO));
    expect(text(block())).not.toMatch(/\bscore\b|\bgrade\b|secure|trend|time to hack/i);
    // Every word in the block is one the backend sent (compared without spaces: the parts are separate elements).
    const squeezed = (words: string) => words.replace(/\s+/g, "");
    let left = squeezed(text(block()));
    const sent = [
      OTTO.title,
      OTTO.pack_line,
      OTTO.note,
      OTTO.since_title ?? "",
      ...OTTO.rows.flatMap((r) => [r.title, r.waiting_text, ...r.since]),
    ];
    for (const words of sent.map(squeezed).sort((a, b) => b.length - a.length)) left = left.split(words).join("");
    expect(left).toBe("");
  });
});
