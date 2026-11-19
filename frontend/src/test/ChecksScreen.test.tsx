import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { CheckDetail, CheckRow, ChecksView, PlanView } from "../api";
import { ChecksScreen } from "../components/ChecksScreen";
import { LinkProvider } from "../components/related";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import {
  CHECKS_SUBLINE,
  NO_RETEST,
  blockRow,
  checkGroups,
  checksView,
  encryptionParts,
  newestBlock,
  olderBlock,
  planRows,
  proofBlock,
  retestDetail,
  retestRow,
  tryRow,
  verifyRows,
} from "./checksFixtures";
import { calls, lab, mockApi, plan, retestRunning, runningPlan, text } from "./fixtures";
import { advisoryCheckRow, blankFailed, relatedOfAdvisoryCheck } from "./ottoFixtures";

const CHECKS = "GET /api/plans/1/checks";
// The 5c fixes: Retest new version is on Checks too. Its state is the one Evidence shows, read from the same view.
const LAB = "GET /api/plans/1/lab";
// The rows of the newest retest's block, as the default view lists them.
const BLOCK_IDS = newestBlock.rows.map((r) => r.id);

function Harness({ group = null, item = null, readOnly = false }: { group?: string | null; item?: string | null; readOnly?: boolean }) {
  const [current, setCurrent] = useState<PlanView | null>(plan);
  return (
    <ReadOnlyProvider readOnly={readOnly}>
      <LinkProvider assessmentId={101} planId={1}>
        <ChecksScreen importId={7} plan={current} onPlan={setCurrent} group={group} openItem={item} />
      </LinkProvider>
    </ReadOnlyProvider>
  );
}

async function open(view: ChecksView = checksView, routes: Parameters<typeof mockApi>[0] = {}, props: Parameters<typeof Harness>[0] = {}) {
  const fetchMock = mockApi({ [CHECKS]: { body: view }, [LAB]: { body: lab }, "GET /api/import/7/plan": { body: plan }, ...routes });
  render(<Harness {...props} />);
  await screen.findAllByTestId("group-section");
  return fetchMock;
}

const section = (key: string) => screen.getAllByTestId("group-section").find((g) => g.getAttribute("data-group") === key)!;
const rowsIn = (key: string) => within(section(key)).queryAllByTestId("check-row");

describe("Checks, the page", () => {
  it("is named Checks, lists every check in the four work groups in order, and keeps the test plan under Encryption tests", async () => {
    const fetchMock = await open();
    expect(screen.getByRole("heading", { level: 1, name: "Checks" })).not.toBeNull();
    expect(text(screen.getByTestId("page-header"))).toContain(CHECKS_SUBLINE);
    expect(screen.getAllByTestId("group-section").map((g) => g.getAttribute("data-group"))).toEqual([
      "verification",
      "encryption",
      "migration",
      "dependencies",
    ]);
    // Verification: one row per claim checked, with the result in Verify's own words.
    expect(rowsIn("verification").map((r) => text(within(r).getByTestId("result-badge")))).toEqual(["False", "True", "? Couldn't check"].map((w) => expect.stringContaining(w.replace("? ", ""))));
    // Encryption tests: the test plan exactly as it was (its cards and buttons), then the other runs (the retest, in
    // the block of the version it ran on).
    expect(within(section("encryption")).getAllByTestId("test-card")).toHaveLength(plan.tests.length);
    expect(within(section("encryption")).getByRole("button", { name: "Run all" })).not.toBeNull();
    expect(within(section("encryption")).getByRole("button", { name: "+ Add test" })).not.toBeNull();
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual(BLOCK_IDS);
    // An empty group stays and says why.
    expect(within(section("migration")).getByTestId("group-empty").textContent).toBe("Nothing measured yet. Measure status is on Migration.");
    expect(within(section("dependencies")).getByTestId("group-empty").textContent).toBe("No dependency list yet. Add one on Dependencies.");
    // The page starts nothing by itself: it only asked for the list.
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("shows each group's three counts and where its checks are started", async () => {
    await open();
    expect(within(section("verification")).getByTestId("group-counts").textContent).toBe("Open 0 · In progress 0 · Done 3");
    expect(within(section("verification")).getByRole("link", { name: "Started on Import" }).getAttribute("href")).toBe("#/a/101/inventory/import");
    expect(within(section("encryption")).getByText("The test plan is here")).not.toBeNull();
    expect(within(section("migration")).getByRole("link", { name: "Started on Migration" }).getAttribute("href")).toBe("#/a/101/migration/systems");
  });

  it("a row shows what ran, on what, where it came from, its result, when it last ran and how many times", async () => {
    await open();
    const row = rowsIn("encryption")[0]!;
    const cells = Array.from(row.children).map((c) => text(c));
    expect(cells).toHaveLength(4);
    expect(Array.from(row.children[0]!.querySelectorAll("span")).map((sp) => sp.textContent)).toEqual([
      "Official test vectors",
      "acme-sign 1.4.3",
    ]);
    expect(cells[1]).toBe("Retest");
    expect(cells[2]).toContain("Passed");
    expect(cells[3]).toMatch(/1 run$/);
    expect(document.body.textContent).not.toMatch(/\bscore\b|\bgrade\b|time to hack/i);
  });

  it("filters by group, by where a check came from, by result and by search", async () => {
    await open();
    fireEvent.change(screen.getByRole("combobox", { name: "Group" }), { target: { value: "verification" } });
    expect(screen.getAllByTestId("group-section").map((g) => g.getAttribute("data-group"))).toEqual(["verification"]);
    fireEvent.change(screen.getByRole("combobox", { name: "Group" }), { target: { value: "all" } });

    fireEvent.change(screen.getByRole("combobox", { name: "Came from" }), { target: { value: "retest" } });
    expect(rowsIn("verification")).toHaveLength(0);
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-came-from"))).toEqual(["retest", "retest", "retest"]);
    expect(within(section("encryption")).getAllByTestId("part-section").map((p) => p.getAttribute("data-part"))).toEqual(["retests"]);
    // Filtered to retests, the test plan itself is not shown.
    expect(within(section("encryption")).queryAllByTestId("test-card")).toHaveLength(0);
    fireEvent.change(screen.getByRole("combobox", { name: "Came from" }), { target: { value: "all" } });

    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "False" } });
    expect(rowsIn("verification").map((r) => r.getAttribute("data-check"))).toEqual(["claim-1"]);
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "all" } });

    fireEvent.change(screen.getByRole("searchbox", { name: "Search checks" }), { target: { value: "certificate" } });
    expect(rowsIn("verification").map((r) => r.getAttribute("data-check"))).toEqual(["claim-2"]);
  });

  it("folds a group shut from its heading", async () => {
    await open();
    fireEvent.click(within(section("verification")).getByRole("button", { name: "Verification" }));
    expect(rowsIn("verification")).toHaveLength(0);
    expect(within(section("verification")).getByTestId("group-counts")).not.toBeNull();
  });

  it("starts filtered to the group a link names", async () => {
    await open(checksView, {}, { group: "encryption" });
    expect(screen.getAllByTestId("group-section").map((g) => g.getAttribute("data-group"))).toEqual(["encryption"]);
  });
});

describe("Checks, a check's panel", () => {
  // A block's row has its own address; the older id of the newest retest still opens the same check.
  const routes = {
    [`GET /api/plans/1/checks/${BLOCK_IDS[0]}`]: { body: { ...retestDetail, check: newestBlock.rows[0]! } },
    [`GET /api/plans/1/checks/${retestRow.id}`]: { body: retestDetail },
  };

  it("opens on a click: the result and plain sentence, where it came from with a link back, the evidence, every run and Related", async () => {
    const fetchMock = await open(checksView, routes);
    fireEvent.click(rowsIn("encryption")[0]!);
    const panel = within(await screen.findByTestId("check-panel"));
    expect(within(screen.getByTestId("detail-panel")).getByRole("heading", { level: 2, name: "Official test vectors" })).not.toBeNull();
    expect(text(screen.getByTestId("check-panel"))).toContain(retestRow.plain!);
    expect(panel.getByTestId("open-where-started").getAttribute("href")).toBe("#/a/101/evidence?item=retest-1");
    expect(panel.getByTestId("see-the-evidence").getAttribute("href")).toBe("#/a/101/evidence?item=retest-1");
    const runs = await panel.findByTestId("earlier-runs");
    expect(within(runs).getAllByRole("listitem").map((li) => text(li))).toEqual([
      expect.stringContaining("Passed"),
      expect.stringContaining("Failed"),
    ]);
    expect(text(runs)).toContain("Test plan");
    const related = within(panel.getByTestId("related"));
    expect(related.getAllByTestId("related-link").map((a) => a.getAttribute("href"))).toEqual([
      "#/a/101/inventory/verify?item=claim-3",
      "#/a/101/fixes?item=fix-ecdsa-range-check",
    ]);
    // Opening a panel starts nothing.
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("opens the check a link names, and the table beside it goes compact", async () => {
    await open(checksView, routes, { item: retestRow.id });
    expect(await screen.findByTestId("check-panel")).not.toBeNull();
    const table = within(section("encryption")).getAllByTestId("data-table").at(-1)!;
    expect(table.getAttribute("data-compact")).toBe("true");
    // the link named the test's retest by its older id: the row of the newest block is the one marked as open
    expect(rowsIn("encryption").filter((r) => r.getAttribute("aria-selected") === "true" || r.getAttribute("data-selected") === "true").map((r) => r.getAttribute("data-check"))).toEqual([BLOCK_IDS[0]]);
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("check-panel")).toBeNull();
  });

  it("asks again every second while a check waits or runs, and stops when nothing runs", async () => {
    let asked = 0;
    const running = { ...checksView, busy: true };
    const fetchMock = mockApi({
      [CHECKS]: () => {
        asked += 1;
        return { body: asked < 3 ? running : checksView };
      },
      [LAB]: { body: lab },
      "GET /api/import/7/plan": { body: plan },
    });
    render(<Harness />);
    await screen.findAllByTestId("group-section");
    await waitFor(() => expect(asked).toBe(3), { timeout: 4000 });
    await new Promise((r) => setTimeout(r, 1200));
    expect(calls(fetchMock).filter((c) => c === CHECKS)).toHaveLength(3);
  });
});

describe("Checks, an advisory check (phase 5c)", () => {
  // The check as the plan lists it: the Advisories page links to it by this id ("Open in Checks").
  const link = blankFailed.panel.here.rows[0]!.checks_link!;
  const check: CheckRow = {
    ...planRows[0]!,
    id: link.item!,
    name: advisoryCheckRow.title,
    link: { page: "checks", item: link.item },
    evidence_link: { page: "evidence", item: link.item },
    plain: advisoryCheckRow.result!.plain,
  };
  const view: ChecksView = { ...checksView, groups: checkGroups({ encryption: [...planRows, check, retestRow] }) };
  const detail: CheckDetail = { ...retestDetail, check, runs: [], related: relatedOfAdvisoryCheck.related };

  it("opens from the address the Advisories page links to, and its Related names the advisory with the way back", async () => {
    expect(link).toEqual({ page: "checks", item: "test-6" });
    const fetchMock = await open(view, { [`GET /api/plans/1/checks/${check.id}`]: { body: detail } }, { item: check.id });
    const panel = within(await screen.findByTestId("check-panel"));
    expect(screen.getByTestId("check-panel").getAttribute("data-check")).toBe(check.id);
    expect(within(screen.getByTestId("detail-panel")).getByRole("heading", { level: 2, name: advisoryCheckRow.title })).not.toBeNull();
    expect(text(screen.getByTestId("check-panel"))).toContain(advisoryCheckRow.result!.plain);
    // The sixth Related line: the advisory, under the backend's title, opening it on Advisories.
    const related = within(await panel.findByTestId("related"));
    const lines = related.getAllByTestId("related-line");
    expect(lines.map((l) => l.getAttribute("data-kind"))).toEqual(relatedOfAdvisoryCheck.related.map((l) => l.kind));
    const advisory = relatedOfAdvisoryCheck.related.at(-1)!;
    expect(advisory.kind).toBe("advisory");
    expect(within(lines.at(-1)!).getByText(advisory.title)).not.toBeNull();
    const back = within(lines.at(-1)!).getByTestId("related-link");
    expect(back.textContent).toBe(advisory.items[0]!.label);
    expect(back.getAttribute("href")).toBe(`#/a/101/advisories?item=${blankFailed.id}`);
    // It is a test of the plan like any other: shown once, as its card, and opening its panel starts nothing.
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual(BLOCK_IDS);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });
});

describe("Checks in a closed assessment", () => {
  it("keeps the list and the panels, and turns off the test plan's buttons with the closed sentence", async () => {
    await open(checksView, {}, { readOnly: true });
    for (const name of ["Run all", "+ Add test"]) {
      const button = within(section("encryption")).getByRole("button", { name }) as HTMLButtonElement;
      expect(button.disabled, name).toBe(true);
      expect(button.getAttribute("title"), name).toBe(CLOSED_SENTENCE);
    }
    expect(rowsIn("verification")).toHaveLength(3);
  });

  it("shows an empty Encryption tests group's reason when nothing has run", async () => {
    await open({ ...checksView, groups: checkGroups({ encryption: [] }) });
    // The test plan still shows (it is where tests start); there are no other runs yet.
    expect(within(section("encryption")).getAllByTestId("test-card")).toHaveLength(plan.tests.length);
    expect(rowsIn("encryption")).toHaveLength(0);
  });
});

describe("Checks, the same measurement and the links between groups (phase 5b, plan decisions 3 and 4)", () => {
  const pqClaim = {
    ...verifyRows[0]!,
    id: "claim-4",
    name: "localhost:8451 is post-quantum",
    ran_on: "localhost:8451",
    same_as: [
      {
        id: "system-server:localhost:8451",
        name: "Post-quantum status",
        ran_on: "localhost:8451",
        group_label: "Migration",
        link: { page: "checks", item: "system-server:localhost:8451" },
        evidence_link: { page: "evidence", item: "system-server:localhost:8451" },
      },
    ],
  };
  const view = (): ChecksView => {
    const groups = checkGroups({ verification: [pqClaim] }).map((g) =>
      g.key === "migration"
        ? {
            ...g,
            also: [
              {
                id: "claim-4",
                name: "localhost:8451 is post-quantum",
                ran_on: "localhost:8451",
                group_label: "Verification",
                link: { page: "checks", item: "claim-4" },
                evidence_link: { page: "evidence", item: "claim-4" },
              },
            ],
          }
        : g,
    );
    return { ...checksView, groups };
  };

  it("marks a row that is the same measurement as another, and names it with a link in its panel", async () => {
    await open(view(), { "GET /api/plans/1/checks/claim-4": { body: { ...retestDetail, check: pqClaim } } });
    const row = rowsIn("verification")[0]!;
    expect(within(row).getByTestId("same-measurement-marker").textContent).toBe("The same measurement as Post-quantum status");
    fireEvent.click(row);
    const same = within(await screen.findByTestId("check-panel")).getByTestId("same-measurement");
    expect(text(same)).toBe("The same measurement as Post-quantum status on localhost:8451 (Migration). Each keeps its own run and its own result.");
    expect(within(same).getByRole("link").getAttribute("href")).toBe("#/a/101/checks?item=system-server%3Alocalhost%3A8451");
  });

  it("links a check of another group from Migration's foot, without listing it twice", async () => {
    await open(view());
    const foot = within(section("migration")).getByTestId("group-also");
    expect(text(foot)).toBe("Also relates to this group: localhost:8451 is post-quantum on localhost:8451 (in Verification; the same measurement as Measure status)");
    expect(within(foot).getByTestId("also-link").getAttribute("href")).toBe("#/a/101/checks?item=claim-4");
    expect(rowsIn("migration")).toHaveLength(0);
    expect(rowsIn("verification")).toHaveLength(1);
  });

  it("shows a test of the plan once, as its card, even when its newest run came right after an Apply", async () => {
    const afterApply = { ...planRows[2]!, came_from: { key: "after_apply", label: "After Apply" } };
    await open({ ...checksView, groups: checkGroups({ encryption: [planRows[0]!, planRows[1]!, afterApply, retestRow] }) });
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual(BLOCK_IDS);
  });

  it("a finished test of the plan links to its result on Evidence", async () => {
    const fetchMock = mockApi({ [CHECKS]: { body: checksView }, [LAB]: { body: lab }, "GET /api/import/7/plan": { body: runningPlan } });
    function Ran() {
      const [current, setCurrent] = useState<PlanView | null>(runningPlan);
      return (
        <LinkProvider assessmentId={101} planId={1}>
          <ChecksScreen importId={7} plan={current} onPlan={setCurrent} />
        </LinkProvider>
      );
    }
    render(<Ran />);
    await screen.findAllByTestId("group-section");
    const done = within(section("encryption")).getAllByTestId("test-card").find((c) => c.getAttribute("data-status") === "done")!;
    expect(within(done).getByTestId("see-the-evidence").getAttribute("href")).toBe(`#/a/101/evidence?item=test-${runningPlan.tests[0]!.id}`);
    // Not-run tests have no such link.
    const notRun = within(section("encryption")).getAllByTestId("test-card").filter((c) => c.getAttribute("data-status") !== "done");
    expect(notRun.every((c) => within(c).queryByTestId("see-the-evidence") === null)).toBe(true);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });
});

describe("Checks, the test plan is drawn once: it is there before the list of checks, and stays as it is when the list arrives", () => {
  const part = (key: string) => within(section("encryption")).getAllByTestId("part-section").find((p) => p.getAttribute("data-part") === key)!;

  it("keeps the + Add test menu open, and the keyboard's place in it, when the list arrives after the menu was opened", async () => {
    // The list of checks answers late (a busy computer). The plan is on the page at once, with its buttons.
    let answer: (r: Response) => void = () => {};
    const late = new Promise<Response>((resolve) => (answer = resolve));
    const fetchMock = mockApi({ [LAB]: { body: lab }, "GET /api/import/7/plan": { body: plan } });
    const answered = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, init) => (String(input) === "/api/plans/1/checks" ? late : answered(input, init)));
    render(<Harness />);
    const add = await screen.findByRole("button", { name: "+ Add test" });
    expect(screen.queryAllByTestId("group-section")).toHaveLength(0); // the list is not here yet
    const cardsBefore = screen.getAllByTestId("test-card");
    add.focus();
    fireEvent.click(add);
    const menu = screen.getByRole("menu");
    const item = within(menu).getAllByRole("menuitem")[0]!;
    item.focus();

    answer(new Response(JSON.stringify(checksView), { status: 200, headers: { "Content-Type": "application/json" } }));
    await screen.findAllByTestId("group-section");
    // the same menu, the same cards and the same focused item: the plan was moved into its part, not drawn again
    expect(screen.getByRole("menu")).toBe(menu);
    expect(part("plan").contains(menu)).toBe(true);
    expect(screen.getAllByTestId("test-card")).toEqual(cardsBefore);
    expect(document.activeElement).toBe(item);
    expect(screen.getAllByRole("button", { name: "+ Add test" })).toHaveLength(1); // and it is on the page once
  });

  it("is not drawn while its part is folded shut or a filter leaves the plan out, and comes back after", async () => {
    await open();
    expect(within(part("plan")).getAllByTestId("test-card")).toHaveLength(plan.tests.length);
    fireEvent.click(within(part("plan")).getByRole("button", { name: /Test plan/ }));
    expect(screen.queryAllByTestId("test-card")).toHaveLength(0);
    fireEvent.click(within(part("plan")).getByRole("button", { name: /Test plan/ }));
    expect(within(part("plan")).getAllByTestId("test-card")).toHaveLength(plan.tests.length);
  });
});

describe("Checks, the test plan is read fresh when the page opens", () => {
  it("asks for the plan (a read, never a write), so a proof that started meanwhile turns Run all off", async () => {
    // The app's copy says Run all can start; the plan as it is now says a proof runs.
    const now = { ...plan, can_run_all: false, running: true };
    const fetchMock = await open(checksView, { "GET /api/import/7/plan": { body: now } });
    await waitFor(() =>
      expect((within(section("encryption")).getByRole("button", { name: "Run all" }) as HTMLButtonElement).disabled).toBe(true),
    );
    expect(calls(fetchMock)).toContain("GET /api/import/7/plan");
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });
});


// The 5c fixes: only the Encryption tests group changes. It has four labelled, foldable parts, each with a count: Test
// plan, Retests by version, Fix proofs, and Tries on a test copy (only when a server change was tried). A run shows in
// one part only.
describe("Checks, Encryption tests in four parts", () => {
  const parts = () => within(section("encryption")).getAllByTestId("part-section");
  const part = (key: string) => parts().find((p) => p.getAttribute("data-part") === key)!;
  const blocksIn = (key: string) => within(part(key)).queryAllByTestId("block-section");
  const withParts = (over: Parameters<typeof encryptionParts>[0]): ChecksView => ({ ...checksView, groups: checkGroups({ parts: encryptionParts(over) }) });

  it("labels each part and gives each its count; Tries on a test copy shows only when a server change was tried", async () => {
    await open(withParts({ retests: [newestBlock, olderBlock], proofs: [proofBlock] }));
    expect(parts().map((p) => p.getAttribute("data-part"))).toEqual(["plan", "retests", "proofs"]);
    expect(parts().map((p) => within(p).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "▾Test plan3 tests",
      "▾Retests by version2 versions",
      "▾Fix proofs1 proof",
    ]);
    expect(parts().map((p) => within(p).getAllByTestId("part-count")[0]!.textContent)).toEqual(["3 tests", "2 versions", "1 proof"]);
    // the other three groups are as they were: no parts in them
    for (const key of ["verification", "migration", "dependencies"]) expect(within(section(key)).queryByTestId("part-section")).toBeNull();
  });

  it("adds Tries on a test copy once a server change was tried", async () => {
    await open(withParts({ tries: [tryRow] }));
    expect(parts().map((p) => p.getAttribute("data-part"))).toEqual(["plan", "retests", "proofs", "tries"]);
    expect(within(part("tries")).getByTestId("part-count").textContent).toBe("1 try");
    expect(within(part("tries")).getAllByTestId("check-row").map((r) => r.getAttribute("data-check"))).toEqual([tryRow.id]);
  });

  it("heads the test plan with the version the file names, and keeps its buttons inside that part", async () => {
    await open();
    expect(within(part("plan")).getByTestId("part-note").textContent).toBe("First runs, on the version the file names: acme-sign 1.4.2.");
    expect(within(part("plan")).getAllByTestId("test-card")).toHaveLength(plan.tests.length);
    for (const name of ["Run all", "+ Add test"]) expect(within(part("plan")).getByRole("button", { name })).not.toBeNull();
    // a first run shows in the plan only: no row of the plan is listed again under the retests
    expect(within(part("retests")).queryAllByTestId("test-card")).toHaveLength(0);
  });

  it("says so before any retest, and has Retest new version on the page", async () => {
    await open(withParts({ retests: [] }));
    expect(within(part("retests")).getByTestId("part-empty").textContent).toBe(NO_RETEST);
    expect(within(part("retests")).getByTestId("part-count").textContent).toBe("0 versions");
    expect(blocksIn("retests")).toHaveLength(0);
    expect(await within(part("retests")).findByRole("button", { name: "Retest new version" })).not.toBeNull();
  });

  it("offers the same menu as Evidence, and choosing a version starts the retest from here", async () => {
    // (once the retest has started, the server's view says so on every read)
    let started = false;
    const fetchMock = await open(checksView, {
      [LAB]: () => ({ body: started ? retestRunning : lab }),
      "POST /api/plans/1/retest": () => {
        started = true;
        return { body: retestRunning };
      },
    });
    fireEvent.click(await within(part("retests")).findByRole("button", { name: "Retest new version" }));
    const menu = within(screen.getByRole("menu", { name: lab.retest.menu_title }));
    const items = menu.getAllByRole("menuitem");
    expect(items).toHaveLength(lab.retest.versions.length);
    lab.retest.versions.forEach((v, i) => {
      for (const words of [v.label, v.tag!, v.note]) expect(text(items[i]!)).toContain(words);
    });
    expect(menu.getByText(lab.retest.menu_note)).not.toBeNull();
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);      // opening the menu runs nothing
    fireEvent.click(menu.getAllByRole("menuitem")[0]!);
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/retest"));
    const sent = fetchMock.mock.calls.find(([url]) => String(url) === "/api/plans/1/retest")![1]!;
    expect(JSON.parse(String(sent.body))).toEqual({ version: "1.4.3", component: "acme-sign" });
    // the page then shows how far the retest is, in the view's own words, and the button is off while it runs
    expect((await within(part("retests")).findByTestId("retest-progress")).textContent).toBe("Retest running: 1 of 5 tests finished.");
    expect((within(part("retests")).getByRole("button", { name: "Retest new version" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("reads the test plan again once a retest has started here, so Run all is off at once and not when the server refuses a click", async () => {
    let started = false;
    const fetchMock = await open(checksView, {
      [LAB]: () => ({ body: started ? retestRunning : lab }),
      "GET /api/import/7/plan": () => ({ body: started ? { ...plan, can_run_all: false, running: true } : plan }),
      "POST /api/plans/1/retest": () => {
        started = true;
        return { body: retestRunning };
      },
    });
    const runAll = () => within(part("plan")).getByRole("button", { name: "Run all" }) as HTMLButtonElement;
    expect(runAll().disabled).toBe(false);
    fireEvent.click(await within(part("retests")).findByRole("button", { name: "Retest new version" }));
    fireEvent.click(within(screen.getByRole("menu", { name: lab.retest.menu_title })).getAllByRole("menuitem")[0]!);
    await waitFor(() => expect(runAll().disabled).toBe(true));
    const sent = calls(fetchMock);
    expect(sent.lastIndexOf("GET /api/import/7/plan")).toBeGreaterThan(sent.indexOf("POST /api/plans/1/retest"));
    expect(sent.filter((c) => c.startsWith("POST"))).toEqual(["POST /api/plans/1/retest"]);      // one start, nothing else
  });

  it("turns the button off with the same reason Evidence gives", async () => {
    const off = { ...lab, retest: { ...lab.retest, can_start: false, blocked_reason: "Run every test first: 2 of 5 have no result yet." } };
    await open(checksView, { [LAB]: { body: off } });
    const button = (await within(part("retests")).findByRole("button", { name: "Retest new version" })) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(within(part("retests")).getByTestId("retest-blocked").textContent).toBe("Run every test first: 2 of 5 have no result yet.");
  });

  it("in a closed assessment the button is off with the closed sentence", async () => {
    await open(checksView, {}, { readOnly: true });
    const button = (await within(part("retests")).findByRole("button", { name: "Retest new version" })) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.getAttribute("title")).toBe(CLOSED_SENTENCE);
  });

  it("shows one block for each version, the newest open and an older one folded until it is opened", async () => {
    await open(withParts({ retests: [newestBlock, olderBlock] }));
    const [newest, older] = blocksIn("retests") as [HTMLElement, HTMLElement];
    expect(within(newest).getByRole("heading", { level: 4 }).textContent).toContain("acme-sign 1.4.3");
    expect(within(newest).getByTestId("block-line").textContent).toBe(newestBlock.line);
    expect(within(newest).getByRole("button").getAttribute("aria-expanded")).toBe("true");
    expect(within(newest).getAllByTestId("check-row").map((r) => r.getAttribute("data-check"))).toEqual(BLOCK_IDS);
    // the older version: its heading is there, its rows are not, until its heading is clicked
    expect(within(older).getByRole("heading", { level: 4 }).textContent).toContain("acme-sign 1.4.3-otto");
    expect(within(older).getByRole("button").getAttribute("aria-expanded")).toBe("false");
    expect(within(older).queryAllByTestId("check-row")).toHaveLength(0);
    fireEvent.click(within(older).getByRole("button"));
    expect(within(older).getAllByTestId("check-row").map((r) => r.getAttribute("data-check"))).toEqual(["retest-1-on-1"]);
    // and the newest folds shut from its heading
    fireEvent.click(within(newest).getByRole("button"));
    expect(within(newest).queryAllByTestId("check-row")).toHaveLength(0);
  });

  it("marks a server test that a retest ran again unchanged", async () => {
    await open();
    const rows = within(part("retests")).getAllByTestId("check-row");
    expect(rows.map((r) => within(r).queryByTestId("check-mark")?.textContent ?? null)).toEqual([null, null, " · tested again as it is"]);
    expect(text(rows[2]!.children[0]!)).toContain("localhost:8443 · tested again as it is");
  });

  it("opens a row of an older block on that block's own run", async () => {
    const detail: CheckDetail = { ...retestDetail, check: olderBlock.rows[0]!, runs: [retestDetail.runs[0]!] };
    const fetchMock = await open(withParts({ retests: [newestBlock, olderBlock] }), { "GET /api/plans/1/checks/retest-1-on-1": { body: detail } });
    fireEvent.click(within(blocksIn("retests")[1]!).getByRole("button"));
    fireEvent.click(within(blocksIn("retests")[1]!).getByTestId("check-row"));
    const panel = await screen.findByTestId("check-panel");
    expect(panel.getAttribute("data-check")).toBe("retest-1-on-1");
    expect(calls(fetchMock)).toContain("GET /api/plans/1/checks/retest-1-on-1");
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("shows one block for each proof, with the changed code's version", async () => {
    await open(withParts({ proofs: [proofBlock] }));
    const [block] = blocksIn("proofs") as [HTMLElement];
    expect(within(block).getByRole("heading", { level: 4 }).textContent).toContain("acme-sign 1.4.3 (the changed code)");
    expect(within(block).getAllByTestId("check-row").map((r) => r.getAttribute("data-check"))).toEqual(["proof-1-in-1"]);
    expect(within(block).getByTestId("check-row").getAttribute("data-came-from")).toBe("proof");
  });

  it("Came from finds a retest's run that came right after an Apply in its block, and never shows a block as empty", async () => {
    // The newest run of this retest's server test came right after an Apply: its row says so in "Came from".
    const afterApply = blockRow(3, 2, "Old TLS versions", "localhost:8443", true, { came_from: { key: "after_apply", label: "After Apply" } });
    const block = { ...newestBlock, rows: [newestBlock.rows[0]!, afterApply] };
    const onlyAfter = { ...olderBlock, rows: [{ ...afterApply, id: "retest-3-on-1", alias: null }] };
    await open(withParts({ retests: [block, onlyAfter] }));
    const from = (value: string) => fireEvent.change(screen.getByRole("combobox", { name: "Came from" }), { target: { value } });

    from("after_apply");
    // the Retests part is there for that row, in the blocks that hold one; the plan and the proofs are not
    expect(parts().map((p) => p.getAttribute("data-part"))).toEqual(["retests"]);
    expect(blocksIn("retests").map((b) => b.getAttribute("data-block"))).toEqual([block.key, onlyAfter.key]);
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual([afterApply.id, "retest-3-on-1"]);
    expect(text(section("encryption"))).not.toContain("Nothing has finished in this block yet.");

    from("retest");
    // the block that holds only the run after the Apply is left out, not shown as a block where nothing finished
    expect(blocksIn("retests").map((b) => b.getAttribute("data-block"))).toEqual([block.key]);
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual([newestBlock.rows[0]!.id]);
    expect(text(section("encryption"))).not.toContain("Nothing has finished in this block yet.");

    from("all");
    expect(parts().map((p) => p.getAttribute("data-part"))).toEqual(["plan", "retests", "proofs"]);
    expect(blocksIn("retests")).toHaveLength(2);
  });

  it("folds a part shut from its heading and keeps its count showing", async () => {
    await open();
    fireEvent.click(within(part("retests")).getByRole("button", { name: /^Retests by version/ }));
    expect(within(part("retests")).queryAllByTestId("check-row")).toHaveLength(0);
    expect(within(part("retests")).getByTestId("part-count").textContent).toBe("1 version");
    fireEvent.click(within(part("plan")).getByRole("button", { name: /^Test plan/ }));
    expect(within(part("plan")).queryAllByTestId("test-card")).toHaveLength(0);
  });

  it("a search opens the block that holds a match and hides a block that holds none", async () => {
    await open(withParts({ retests: [newestBlock, olderBlock] }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search checks" }), { target: { value: "1.4.3-otto" } });
    expect(blocksIn("retests").map((b) => b.getAttribute("data-block"))).toEqual(["on-1"]);
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual(["retest-1-on-1"]);
  });
});
