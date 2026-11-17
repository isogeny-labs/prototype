import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { ChecksView, PlanView } from "../api";
import { ChecksScreen } from "../components/ChecksScreen";
import { LinkProvider } from "../components/related";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { CHECKS_SUBLINE, checkGroups, checksView, planRows, retestDetail, retestRow, verifyRows } from "./checksFixtures";
import { calls, mockApi, plan, runningPlan, text } from "./fixtures";

const CHECKS = "GET /api/plans/1/checks";

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
  const fetchMock = mockApi({ [CHECKS]: { body: view }, "GET /api/import/7/plan": { body: plan }, ...routes });
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
    // Encryption tests: the test plan exactly as it was (its cards and buttons), then the other runs (the retest).
    expect(within(section("encryption")).getAllByTestId("test-card")).toHaveLength(plan.tests.length);
    expect(within(section("encryption")).getByRole("button", { name: "Run all" })).not.toBeNull();
    expect(within(section("encryption")).getByRole("button", { name: "+ Add test" })).not.toBeNull();
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual([retestRow.id]);
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
      "acme-sign 1.4.3 (the new version)",
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
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-came-from"))).toEqual(["retest"]);
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
  const routes = { [`GET /api/plans/1/checks/${retestRow.id}`]: { body: retestDetail } };

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
      "GET /api/import/7/plan": { body: plan },
    });
    render(<Harness />);
    await screen.findAllByTestId("group-section");
    await waitFor(() => expect(asked).toBe(3), { timeout: 4000 });
    await new Promise((r) => setTimeout(r, 1200));
    expect(calls(fetchMock).filter((c) => c === CHECKS)).toHaveLength(3);
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
    expect(rowsIn("encryption").map((r) => r.getAttribute("data-check"))).toEqual([retestRow.id]);
  });

  it("a finished test of the plan links to its result on Evidence", async () => {
    const fetchMock = mockApi({ [CHECKS]: { body: checksView }, "GET /api/import/7/plan": { body: runningPlan } });
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

